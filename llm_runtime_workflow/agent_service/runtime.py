from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .briefing import (
    build_metadata,
    derive_local_signals,
    extract_json_object,
    load_inputs,
    normalize_spoken_text,
    render_spec_markdown,
    validate_text,
    write_json,
)
from .client import ModelHubClient


@dataclass
class AgentResult:
    agent_name: str
    content: str
    parsed: dict[str, Any]
    model: str
    usage: dict[str, Any]


@dataclass
class ArtifactStore:
    root: Path

    def __post_init__(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        (self.root / "agent_outputs").mkdir(exist_ok=True)

    def write_text(self, relative_path: str, text: str) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def write_json(self, relative_path: str, data: Any) -> None:
        path = self.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, data)


@dataclass
class LlmAgent:
    name: str
    prompt_path: Path
    client: ModelHubClient
    max_tokens: int

    def run_json(self, payload: dict[str, Any], store: ArtifactStore, step_name: str) -> AgentResult:
        prompt = self.prompt_path.read_text(encoding="utf-8")
        response = self.client.chat(
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": json.dumps(payload, indent=2, ensure_ascii=False)},
            ],
            max_tokens=self.max_tokens,
        )
        try:
            parsed = extract_json_object(response.content)
        except json.JSONDecodeError:
            parsed = {
                "parse_error": True,
                "raw_response": response.content,
            }

        store.write_text(f"agent_outputs/{step_name}.raw.txt", response.content.strip() + "\n")
        store.write_json(
            f"agent_outputs/{step_name}.meta.json",
            {
                "agent": self.name,
                "model": response.model,
                "usage": response.usage,
                "parsed": not parsed.get("parse_error", False),
            },
        )
        if not parsed.get("parse_error", False):
            store.write_json(f"agent_outputs/{step_name}.json", parsed)

        return AgentResult(
            agent_name=self.name,
            content=response.content,
            parsed=parsed,
            model=response.model,
            usage=response.usage,
        )


@dataclass
class MultiAgentOrchestrator:
    project_root: Path
    output_dir: Path
    client: ModelHubClient
    max_repair_rounds: int = 1
    trace: list[dict[str, Any]] = field(default_factory=list)

    @property
    def prompt_dir(self) -> Path:
        return self.project_root / "llm_runtime_workflow" / "prompts"

    def _agent(self, name: str, prompt_filename: str, max_tokens: int) -> LlmAgent:
        return LlmAgent(
            name=name,
            prompt_path=self.prompt_dir / prompt_filename,
            client=self.client,
            max_tokens=max_tokens,
        )

    def _judge_accepts(self, judge_report: dict[str, Any], validation: dict[str, Any]) -> bool:
        if not validation["passed"]:
            return False
        findings = judge_report.get("findings", [])
        p0 = sum(1 for finding in findings if str(finding.get("severity", "")).upper() == "P0")
        p1 = sum(1 for finding in findings if str(finding.get("severity", "")).upper() == "P1")
        return p0 == 0 and p1 <= 1

    def run(self) -> dict[str, Any]:
        store = ArtifactStore(self.output_dir)
        inputs = load_inputs(self.project_root)
        local_signals = derive_local_signals(inputs)
        raw_prompt = (self.project_root / "README_RAW.md").read_text(encoding="utf-8")

        store.write_json(
            "run_config.json",
            {
                "workflow": "gemini_multi_agent_service",
                "model": self.client.model,
                "base_url": self.client.base_url,
                "thinking_budget": self.client.thinking_budget,
                "max_repair_rounds": self.max_repair_rounds,
                "privacy_note": "This run sends calendar, email, news, and profile-derived content to the configured ModelHub endpoint.",
            },
        )

        pm_agent = self._agent("PM Agent", "01_pm_agent.md", max_tokens=5000)
        writer_agent = self._agent("Writer Agent", "02_writer_agent.md", max_tokens=1800)
        judge_agent = self._agent("User Judge Agent", "03_user_judge_agent.md", max_tokens=2500)
        repair_agent = self._agent("Repair Agent", "04_repair_agent.md", max_tokens=1800)

        pm_result = pm_agent.run_json(
            {
                "task": "Extract the daily briefing product spec and priority plan from the raw inputs.",
                "original_prompt": raw_prompt,
                "inputs": inputs,
                "local_preflight_signals": local_signals,
            },
            store,
            "01_pm_agent",
        )
        spec = pm_result.parsed
        if spec.get("parse_error"):
            raise RuntimeError("PM Agent did not return valid JSON; see agent_outputs/01_pm_agent.raw.txt")
        store.write_json("SPEC.json", spec)
        store.write_text("SPEC.md", render_spec_markdown(spec))
        store.write_json("local_preflight_signals.json", local_signals)

        writer_payload = {
            "task": "Write the spoken briefing and coverage claims from the PM spec.",
            "profile": inputs["profile"],
            "calendar_date": inputs["calendar"]["date"],
            "pm_spec": spec,
        }
        writer_result = writer_agent.run_json(writer_payload, store, "02_writer_agent_round_0")
        writer_output = self._require_writer_output(writer_result.parsed, "Writer Agent")

        final_judge_report: dict[str, Any] = {}
        final_metadata: dict[str, Any] = {}
        final_validation: dict[str, Any] = {}
        accepted = False
        round_index = 0

        while True:
            briefing_text = normalize_spoken_text(writer_output["briefing_text"])
            final_validation = validate_text(briefing_text, inputs["profile"])
            interim_metadata = build_metadata(
                workflow="gemini_multi_agent_service",
                model=self.client.model,
                inputs=inputs,
                spec=spec,
                writer_output=writer_output,
                validation=final_validation,
                judge_report=final_judge_report or None,
                round_index=round_index,
            )
            store.write_text(f"rounds/round_{round_index}/briefing.txt", briefing_text + "\n")
            store.write_json(f"rounds/round_{round_index}/briefing.json", interim_metadata)

            judge_result = judge_agent.run_json(
                {
                    "task": "Review the candidate daily briefing as Jordan Chen.",
                    "original_inputs": inputs,
                    "pm_spec": spec,
                    "briefing_text": briefing_text,
                    "metadata": interim_metadata,
                    "local_validation": final_validation,
                    "stop_criteria": "Accept when validation passes, there are no P0 findings, and there is at most one P1 finding.",
                },
                store,
                f"03_user_judge_round_{round_index}",
            )
            final_judge_report = judge_result.parsed
            if final_judge_report.get("parse_error"):
                final_judge_report = {
                    "verdict": "parse_error",
                    "review_markdown": judge_result.content,
                    "findings": [
                        {
                            "severity": "P1",
                            "category": "metadata",
                            "finding": "Judge Agent response was not valid JSON.",
                            "evidence": "See raw judge response.",
                            "user_impact": "The orchestration loop cannot confidently stop.",
                            "recommendation": "Repair once, then require human review.",
                        }
                    ],
                    "top_requested_fixes": ["Return valid JSON from Judge Agent."],
                }

            final_metadata = build_metadata(
                workflow="gemini_multi_agent_service",
                model=self.client.model,
                inputs=inputs,
                spec=spec,
                writer_output=writer_output,
                validation=final_validation,
                judge_report=final_judge_report,
                round_index=round_index,
            )
            accepted = self._judge_accepts(final_judge_report, final_validation)
            self.trace.append(
                {
                    "round_index": round_index,
                    "validation_passed": final_validation["passed"],
                    "validation_issues": final_validation["issues"],
                    "judge_verdict": final_judge_report.get("verdict"),
                    "accepted": accepted,
                }
            )
            if accepted or round_index >= self.max_repair_rounds:
                break

            repair_result = repair_agent.run_json(
                {
                    "task": "Repair the briefing using judge feedback and local validation issues.",
                    "profile": inputs["profile"],
                    "pm_spec": spec,
                    "previous_writer_output": writer_output,
                    "previous_briefing_text": briefing_text,
                    "previous_metadata": final_metadata,
                    "local_validation": final_validation,
                    "judge_report": final_judge_report,
                },
                store,
                f"04_repair_agent_round_{round_index + 1}",
            )
            writer_output = self._require_writer_output(repair_result.parsed, "Repair Agent")
            round_index += 1

        final_text = normalize_spoken_text(writer_output["briefing_text"])
        store.write_text("briefing.txt", final_text + "\n")
        store.write_json("briefing.json", final_metadata)
        store.write_text("review.md", str(final_judge_report.get("review_markdown", "")).strip() + "\n")
        store.write_json("review_report.json", final_judge_report)
        store.write_json("trace.json", self.trace)
        store.write_text(
            "run_summary.md",
            self._render_run_summary(final_validation, final_judge_report, accepted, round_index),
        )

        return {
            "output_dir": str(self.output_dir),
            "accepted": accepted,
            "round_index": round_index,
            "validation": final_validation,
            "judge_verdict": final_judge_report.get("verdict"),
        }

    def _require_writer_output(self, parsed: dict[str, Any], agent_name: str) -> dict[str, Any]:
        if parsed.get("parse_error"):
            raise RuntimeError(f"{agent_name} did not return valid JSON; inspect agent_outputs.")
        briefing_text = parsed.get("briefing_text")
        if not isinstance(briefing_text, str) or not briefing_text.strip():
            raise RuntimeError(f"{agent_name} returned JSON without a non-empty briefing_text.")
        parsed["briefing_text"] = normalize_spoken_text(briefing_text)
        parsed.setdefault("coverage_claims", {"calendar": [], "emails": [], "news": []})
        parsed.setdefault("sections", [])
        return parsed

    def _render_run_summary(
        self,
        validation: dict[str, Any],
        judge_report: dict[str, Any],
        accepted: bool,
        round_index: int,
    ) -> str:
        findings = judge_report.get("findings", [])
        lines = [
            "# Gemini Multi-Agent Run Summary",
            "",
            f"- accepted: `{accepted}`",
            f"- final round: `{round_index}`",
            f"- judge verdict: `{judge_report.get('verdict')}`",
            f"- estimated seconds: `{validation['estimated_seconds']}`",
            f"- word count: `{validation['word_count']}`",
            f"- validation passed: `{validation['passed']}`",
            "",
            "## Validation Issues",
        ]
        if validation["issues"]:
            lines.extend(f"- {issue}" for issue in validation["issues"])
        else:
            lines.append("- None")
        lines.extend(["", "## Judge Findings"])
        if findings:
            for finding in findings:
                lines.append(f"- **{finding.get('severity')} {finding.get('category')}**: {finding.get('finding')}")
        else:
            lines.append("- None")
        return "\n".join(lines).strip() + "\n"
