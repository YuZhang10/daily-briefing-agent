#!/usr/bin/env python3
"""Run the Gemini-backed multi-agent briefing service."""

from __future__ import annotations

import argparse
import os
from pathlib import Path

from agent_service.client import ModelHubClient
from agent_service.runtime import MultiAgentOrchestrator


SCRIPT_ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_ROOT.parent


def load_local_env(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Gemini multi-agent daily briefing service.")
    parser.add_argument(
        "--output-name",
        default="gemini_multi_agent_1",
        help="Subdirectory name under llm_runtime_workflow/outputs/.",
    )
    parser.add_argument(
        "--max-repair-rounds",
        type=int,
        default=1,
        help="Maximum number of judge-driven repair rounds after the first writer attempt.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    load_local_env(PROJECT_ROOT / ".env")
    output_dir = SCRIPT_ROOT / "outputs" / args.output_name
    client = ModelHubClient.from_env()
    orchestrator = MultiAgentOrchestrator(
        project_root=PROJECT_ROOT,
        output_dir=output_dir,
        client=client,
        max_repair_rounds=args.max_repair_rounds,
    )
    print("Running Gemini-backed PM -> Writer -> Judge -> optional Repair workflow.")
    print("Privacy note: this sends profile, calendar, email, and news-derived content to the configured ModelHub endpoint.")
    result = orchestrator.run()
    relative = Path(result["output_dir"]).relative_to(PROJECT_ROOT)
    print(f"Wrote outputs to {relative}")
    print(f"Accepted: {result['accepted']}")
    print(f"Final round: {result['round_index']}")
    print(f"Estimated duration: {result['validation']['estimated_seconds']} seconds")
    print(f"Word count: {result['validation']['word_count']}")
    print(f"Validation passed: {result['validation']['passed']}")
    print(f"Judge verdict: {result['judge_verdict']}")
    if result["validation"]["issues"]:
        print("Validation issues:")
        for issue in result["validation"]["issues"]:
            print(f"- {issue}")


if __name__ == "__main__":
    main()
