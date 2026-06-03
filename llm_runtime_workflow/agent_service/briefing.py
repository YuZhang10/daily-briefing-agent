from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any


SOURCE_KEYS = {
    "calendar": "events",
    "emails": "emails",
    "news": "items",
}
WORDS_PER_MINUTE = 150


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def load_inputs(project_root: Path) -> dict[str, Any]:
    input_dir = project_root / "inputs"
    return {
        "profile": load_json(input_dir / "profile.json"),
        "calendar": load_json(input_dir / "calendar.json"),
        "emails": load_json(input_dir / "emails.json"),
        "news": load_json(input_dir / "news.json"),
    }


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value)


def _item_text(item: dict[str, Any]) -> str:
    pieces: list[str] = []
    for key in ("title", "subject", "summary", "description", "source"):
        value = item.get(key)
        if isinstance(value, str):
            pieces.append(value)
    sender = item.get("from")
    if isinstance(sender, dict):
        pieces.extend(str(v) for v in sender.values())
    return " ".join(pieces).lower()


def derive_local_signals(inputs: dict[str, Any]) -> dict[str, Any]:
    """Local deterministic hints that help the PM Agent avoid obvious misses."""
    events = inputs["calendar"]["events"]
    emails = inputs["emails"]["emails"]
    news_items = inputs["news"]["items"]
    tracked_entities = [entity["name"] for entity in inputs["profile"].get("tracked_entities", [])]

    conflicts: list[dict[str, Any]] = []
    for left_index, left in enumerate(events):
        left_start = _parse_datetime(left["start"])
        left_end = _parse_datetime(left["end"])
        for right in events[left_index + 1 :]:
            right_start = _parse_datetime(right["start"])
            right_end = _parse_datetime(right["end"])
            if left_start < right_end and right_start < left_end:
                conflicts.append(
                    {
                        "calendar_ids": [left["id"], right["id"]],
                        "titles": [left["title"], right["title"]],
                        "reason": "calendar overlap; listener may need to move or choose one commitment",
                    }
                )

    action_required_emails = [
        {
            "id": email["id"],
            "subject": email["subject"],
            "labels": email.get("labels", []),
            "summary": email["summary"],
        }
        for email in emails
        if "action-required" in email.get("labels", []) or "action required" in email["subject"].lower()
    ]
    customer_escalations = [
        {
            "id": email["id"],
            "subject": email["subject"],
            "summary": email["summary"],
        }
        for email in emails
        if "escalation" in email["subject"].lower() or "top-20 enterprise customer" in email["summary"].lower()
    ]
    prep_keywords = (
        "asks",
        "come with",
        "recommendation",
        "review",
        "before",
        "please read",
        "requests product input",
        "deadline",
    )
    meeting_prep_requests = [
        {
            "id": email["id"],
            "subject": email["subject"],
            "summary": email["summary"],
            "reason": "email implies same-day preparation, owner input, or a deadline",
        }
        for email in emails
        if any(keyword in _item_text(email) for keyword in prep_keywords)
    ]
    private_items = [
        {
            "source": "calendar",
            "id": event["id"],
            "title": event["title"],
            "reason": "calendar item marked private",
        }
        for event in events
        if event.get("visibility") == "private"
    ] + [
        {
            "source": "emails",
            "id": email["id"],
            "subject": email["subject"],
            "reason": "personal or medical email should not be read in detail",
        }
        for email in emails
        if "personal" in email.get("labels", []) and ("medical" in email["summary"].lower() or "appointment" in email["summary"].lower())
    ]

    tracked_hits: dict[str, dict[str, list[str]]] = {}
    for entity in tracked_entities:
        entity_key = entity.lower()
        hits = {"calendar": [], "emails": [], "news": []}
        for event in events:
            if entity_key in _item_text(event):
                hits["calendar"].append(event["id"])
        for email in emails:
            if entity_key in _item_text(email):
                hits["emails"].append(email["id"])
        for item in news_items:
            if entity_key in _item_text(item):
                hits["news"].append(item["id"])
        if any(hits.values()):
            tracked_hits[entity] = hits

    drop_candidates = []
    for item in news_items:
        text = _item_text(item)
        if any(term in text for term in ("lakers", "fa cup", "taylor swift", "avengers")):
            drop_candidates.append({"source": "news", "id": item["id"], "reason": "sports or entertainment"})
        if "bitcoin" in text and ("price" in text or "$" in text or "traded above" in text):
            drop_candidates.append({"source": "news", "id": item["id"], "reason": "day-to-day crypto price movement"})

    return {
        "calendar_conflicts": conflicts,
        "action_required_emails": action_required_emails,
        "customer_escalations": customer_escalations,
        "meeting_prep_requests": meeting_prep_requests,
        "private_items": private_items,
        "tracked_entity_hits": tracked_hits,
        "drop_candidates": drop_candidates,
    }


def extract_json_object(text: str) -> dict[str, Any]:
    cleaned = text.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(cleaned[start : end + 1])


def normalize_spoken_text(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:text)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text))


def estimate_seconds(text: str) -> int:
    return round(word_count(text) / WORDS_PER_MINUTE * 60)


def validate_text(text: str, profile: dict[str, Any]) -> dict[str, Any]:
    length = profile["audio_length_seconds"]
    seconds = estimate_seconds(text)
    issues: list[str] = []

    if re.search(r"https?://|www\.", text):
        issues.append("contains URL")
    if re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", text):
        issues.append("contains email address")
    if re.search(r"(^|\n)\s*[-*#]", text):
        issues.append("contains markdown-like marker")
    if re.search(r"\$|%|\b\d", text):
        issues.append("contains numeric shorthand that may not be TTS-friendly")
    if seconds < length["min"] or seconds > length["max"]:
        issues.append(f"estimated duration outside profile range of {length['min']} to {length['max']} seconds")

    sensitive_terms = [
        "Sutter Health",
        "appointments@sutterhealth.org",
        "medical appointment",
        "Mom's surprise birthday",
        "surprise birthday",
        "birthday plans",
        "birthday",
    ]
    for term in sensitive_terms:
        if term.lower() in text.lower():
            issues.append(f"contains sensitive private detail: {term}")

    return {
        "word_count": word_count(text),
        "estimated_seconds": seconds,
        "words_per_minute": WORDS_PER_MINUTE,
        "profile_min_seconds": length["min"],
        "profile_target_seconds": length["target"],
        "profile_max_seconds": length["max"],
        "issues": issues,
        "passed": not issues,
    }


def all_source_ids(inputs: dict[str, Any]) -> dict[str, set[str]]:
    return {
        source: {item["id"] for item in inputs[source][container]}
        for source, container in SOURCE_KEYS.items()
    }


def normalize_coverage(raw: Any, inputs: dict[str, Any]) -> dict[str, list[str]]:
    valid = all_source_ids(inputs)
    normalized: dict[str, list[str]] = {source: [] for source in SOURCE_KEYS}
    if not isinstance(raw, dict):
        return normalized
    for source in SOURCE_KEYS:
        values = raw.get(source, [])
        if not isinstance(values, list):
            continue
        normalized[source] = sorted({item_id for item_id in values if item_id in valid[source]})
    return normalized


def merge_coverage(a: dict[str, list[str]], b: dict[str, list[str]]) -> dict[str, list[str]]:
    return {
        source: sorted(set(a.get(source, [])) | set(b.get(source, [])))
        for source in SOURCE_KEYS
    }


def section_ranges(text: str, writer_sections: Any, inputs: dict[str, Any], total_coverage: dict[str, list[str]]) -> list[dict[str, Any]]:
    paragraphs = [p for p in text.split("\n\n") if p.strip()]
    if not paragraphs:
        return []

    use_writer_sections = isinstance(writer_sections, list) and len(writer_sections) == len(paragraphs)
    sections: list[dict[str, Any]] = []
    cursor = 0
    for index, paragraph in enumerate(paragraphs):
        start = text.find(paragraph, cursor)
        end = start + len(paragraph)
        if use_writer_sections:
            raw_section = writer_sections[index]
            name = str(raw_section.get("name", f"paragraph_{index + 1}"))
            coverage = normalize_coverage(raw_section.get("covered_item_ids", {}), inputs)
        else:
            name = "briefing" if len(paragraphs) == 1 else f"paragraph_{index + 1}"
            coverage = total_coverage if index == 0 else {source: [] for source in SOURCE_KEYS}
        sections.append(
            {
                "name": name,
                "start_char": start,
                "end_char": end,
                "covered_item_ids": coverage,
            }
        )
        cursor = end
    return sections


def dropped_items_from_spec(spec: dict[str, Any], covered: dict[str, list[str]]) -> list[dict[str, Any]]:
    covered_set = {item_id for ids in covered.values() for item_id in ids}
    plan = spec.get("briefing_plan", {})
    dropped: list[dict[str, Any]] = []

    for bundle in plan.get("must_include_bundles", []):
        source_ids = bundle.get("source_ids", {})
        ids = [item_id for ids_for_source in source_ids.values() for item_id in ids_for_source]
        if ids and not any(item_id in covered_set for item_id in ids):
            dropped.append(
                {
                    "bundle_id": bundle.get("bundle_id"),
                    "priority": bundle.get("priority", "unknown"),
                    "source_ids": source_ids,
                    "reason": "not included by LLM writer within the sixty-to-ninety-second budget",
                }
            )

    for rule in plan.get("drop_rules", []) + plan.get("must_drop", []):
        dropped.append(
            {
                "priority": rule.get("priority", "P3"),
                "source_ids": rule.get("source_ids", {}),
                "reason": rule.get("reason", "dropped by PM policy"),
            }
        )
    return dropped


def build_metadata(
    *,
    workflow: str,
    model: str,
    inputs: dict[str, Any],
    spec: dict[str, Any],
    writer_output: dict[str, Any],
    validation: dict[str, Any],
    judge_report: dict[str, Any] | None,
    round_index: int,
) -> dict[str, Any]:
    text = normalize_spoken_text(str(writer_output.get("briefing_text", "")))
    coverage = normalize_coverage(writer_output.get("coverage_claims", {}), inputs)
    sections = section_ranges(text, writer_output.get("sections"), inputs, coverage)
    section_coverage = {source: [] for source in SOURCE_KEYS}
    for section in sections:
        section_coverage = merge_coverage(section_coverage, section["covered_item_ids"])
    coverage = merge_coverage(coverage, section_coverage)

    return {
        "workflow": workflow,
        "model": model,
        "round_index": round_index,
        "date": inputs["calendar"]["date"],
        "timezone": inputs["calendar"]["timezone"],
        "generated_for": {
            "user": inputs["profile"]["user"]["name"],
            "role": inputs["profile"]["user"]["role"],
            "team": inputs["profile"]["user"]["team"],
        },
        "duration_estimate": {
            "estimated_seconds": validation["estimated_seconds"],
            "word_count": validation["word_count"],
            "method": "word_count / 150 words per minute * 60",
        },
        "covered_item_ids": coverage,
        "sections": sections,
        "dropped_items": dropped_items_from_spec(spec, coverage),
        "validation": validation,
        "judge_verdict": (judge_report or {}).get("verdict"),
        "notes": [
            "PM, Writer, Judge, and optional Repair agents call the configured Gemini-compatible ModelHub endpoint.",
            "Coverage is claimed by the writer and normalized against known input IDs.",
            "Local validation remains deterministic so model prose cannot silently violate TTS constraints.",
        ],
    }


def render_spec_markdown(spec: dict[str, Any]) -> str:
    lines = ["# Runtime PM Spec", ""]
    lines.append(spec.get("spec_summary", "No summary returned."))
    lines.append("")
    lines.append("## Priority Policy")
    policy = spec.get("priority_policy", {})
    if isinstance(policy, dict):
        for key, value in policy.items():
            lines.append(f"- `{key}`: {value}")
    lines.append("")
    lines.append("## Must Include Bundles")
    bundles = spec.get("briefing_plan", {}).get("must_include_bundles", [])
    for bundle in bundles:
        source_ids = json.dumps(bundle.get("source_ids", {}), ensure_ascii=False)
        lines.append(f"- **{bundle.get('priority', 'P?')} {bundle.get('bundle_id', 'bundle')}**: {bundle.get('speaker_goal', bundle.get('why', ''))}")
        lines.append(f"  - source ids: `{source_ids}`")
    lines.append("")
    lines.append("## Acceptance Criteria")
    for item in spec.get("acceptance_criteria", []):
        lines.append(f"- {item}")
    return "\n".join(lines).strip() + "\n"
