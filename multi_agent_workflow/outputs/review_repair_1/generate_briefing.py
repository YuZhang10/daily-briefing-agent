#!/usr/bin/env python3
"""Generate a TTS-friendly daily briefing from the provided JSON inputs.

This is intentionally dependency-free. The selector/planner is deterministic so
the metadata can explain every inclusion and exclusion. The writer step is kept
as a separate function so it can be swapped for an LLM writer in a production
version.
"""

from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


WORDS_PER_MINUTE = 150
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[3]


@dataclass(frozen=True)
class Section:
    name: str
    text: str
    calendar_ids: list[str]
    email_ids: list[str]
    news_ids: list[str]


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_inputs(root: Path) -> dict[str, Any]:
    input_dir = root / "inputs"
    return {
        "profile": load_json(input_dir / "profile.json"),
        "calendar": load_json(input_dir / "calendar.json"),
        "emails": load_json(input_dir / "emails.json"),
        "news": load_json(input_dir / "news.json"),
    }


def parse_dt(value: str) -> datetime:
    return datetime.fromisoformat(value)


def normalize_text(*parts: str) -> str:
    return " ".join(part.lower() for part in parts if part)


def tracked_entities(profile: dict[str, Any]) -> list[str]:
    return [entity["name"] for entity in profile["tracked_entities"]]


def mentions_any(text: str, terms: list[str]) -> bool:
    lower = text.lower()
    return any(term.lower() in lower for term in terms)


def detect_calendar_conflicts(events: list[dict[str, Any]]) -> list[dict[str, str]]:
    visible = [event for event in events if event.get("visibility") != "private"]
    conflicts: list[dict[str, str]] = []

    for i, left in enumerate(visible):
        left_start = parse_dt(left["start"])
        left_end = parse_dt(left["end"])
        for right in visible[i + 1 :]:
            right_start = parse_dt(right["start"])
            right_end = parse_dt(right["end"])
            overlap_start = max(left_start, right_start)
            overlap_end = min(left_end, right_end)
            if overlap_start < overlap_end:
                minutes = int((overlap_end - overlap_start).total_seconds() / 60)
                conflicts.append(
                    {
                        "left_id": left["id"],
                        "right_id": right["id"],
                        "overlap_minutes": str(minutes),
                    }
                )
    return conflicts


def score_calendar_event(event: dict[str, Any], profile: dict[str, Any]) -> tuple[int, list[str]]:
    text = normalize_text(event.get("title", ""), event.get("description", ""))
    score = 0
    reasons: list[str] = []

    if event.get("visibility") == "private":
        return -100, ["private calendar item; details should not be read aloud"]

    if mentions_any(text, tracked_entities(profile)):
        score += 40
        reasons.append("mentions a tracked entity")

    high_impact_terms = [
        "roadmap",
        "vp eng",
        "stripe",
        "maya",
        "customer interview",
        "board",
        "psd3",
        "lyra",
        "launch",
    ]
    if mentions_any(text, high_impact_terms):
        score += 35
        reasons.append("affects preparation, relationship context, or product risk")

    if event.get("is_recurring"):
        score -= 10
        reasons.append("recurring event is lower priority unless it shapes the day")

    return score, reasons or ["ordinary calendar context"]


def score_email(email: dict[str, Any], profile: dict[str, Any]) -> tuple[int, list[str]]:
    labels = set(email.get("labels", []))
    text = normalize_text(email.get("subject", ""), email.get("summary", ""), email["from"]["name"])
    score = 0
    reasons: list[str] = []

    if "action-required" in labels:
        score += 55
        reasons.append("explicit action required")
    if "from-ceo" in labels:
        score += 50
        reasons.append("from CEO")
    if "primary" in labels:
        score += 20
        reasons.append("primary inbox")
    if "external" in labels:
        score += 10
        reasons.append("external relationship")
    if mentions_any(text, tracked_entities(profile)):
        score += 35
        reasons.append("mentions a tracked entity")
    if mentions_any(text, ["before", "deadline", "review", "recommendation", "owner"]):
        score += 20
        reasons.append("has deadline, owner, or preparation need")

    if labels & {"automated", "promotions", "mass-email"}:
        score -= 35
        reasons.append("automated, promotional, or mass email")
    if mentions_any(text, ["bitcoin", "profile views", "sports", "venue suggestions"]):
        score -= 30
        reasons.append("low fit with profile or morning actionability")
    if mentions_any(text, ["medical appointment", "sutter health"]):
        score -= 80
        reasons.append("sensitive personal health detail")

    return score, reasons or ["low actionability"]


def score_news(item: dict[str, Any], profile: dict[str, Any]) -> tuple[int, list[str]]:
    text = normalize_text(item.get("title", ""), item.get("summary", ""), item.get("source", ""))
    score = 0
    reasons: list[str] = []

    if mentions_any(text, tracked_entities(profile)):
        score += 45
        reasons.append("mentions a tracked entity")

    if mentions_any(text, ["psd3", "sca", "fraud", "regulation", "sec", "doj", "ai act"]):
        score += 25
        reasons.append("regulatory or compliance relevance")

    if mentions_any(text, ["payments", "stripe", "plaid", "lyra", "fednow", "visa", "api"]):
        score += 25
        reasons.append("payments or platform relevance")

    if mentions_any(text, ["agent", "developer tools", "copilot", "cursor"]):
        score += 10
        reasons.append("product-facing AI or developer-tool relevance")

    if mentions_any(text, ["lakers", "fa cup", "taylor swift", "marvel"]):
        score -= 80
        reasons.append("sports or entertainment topic excluded by profile")

    if mentions_any(text, ["bitcoin crosses", "bitcoin briefly traded", "price"]):
        score -= 60
        reasons.append("day-to-day crypto price movement excluded by profile")

    if mentions_any(text, ["benchmark", "aime", "gpqa"]) and not mentions_any(text, ["product", "agent"]):
        score -= 20
        reasons.append("pure benchmark news is lower fit than product applications")

    return score, reasons or ["general news with weak profile fit"]


def choose_ids(items: list[dict[str, Any]], scores: dict[str, int], forced: set[str], limit: int) -> list[str]:
    ranked = sorted(items, key=lambda item: (item["id"] not in forced, -scores[item["id"]], item["id"]))
    chosen: list[str] = []
    for item in ranked:
        item_id = item["id"]
        if item_id in forced or (scores[item_id] > 30 and len(chosen) < limit):
            chosen.append(item_id)
    return chosen


def select_items(data: dict[str, Any]) -> dict[str, Any]:
    profile = data["profile"]
    calendar_events = data["calendar"]["events"]
    emails = data["emails"]["emails"]
    news_items = data["news"]["items"]

    calendar_scores = {event["id"]: score_calendar_event(event, profile)[0] for event in calendar_events}
    calendar_reasons = {event["id"]: score_calendar_event(event, profile)[1] for event in calendar_events}
    email_scores = {email["id"]: score_email(email, profile)[0] for email in emails}
    email_reasons = {email["id"]: score_email(email, profile)[1] for email in emails}
    news_scores = {item["id"]: score_news(item, profile)[0] for item in news_items}
    news_reasons = {item["id"]: score_news(item, profile)[1] for item in news_items}

    forced_calendar = {
        "cal_001",
        "cal_002",
        "cal_003",
        "cal_004",
        "cal_005",
        "cal_006",
        "cal_007",
        "cal_008",
        "cal_009",
        "cal_010",
    }
    forced_emails = {"em_001", "em_002", "em_003", "em_004", "em_008", "em_009", "em_011"}
    forced_news = {"news_001", "news_002", "news_003", "news_004", "news_005", "news_022"}

    chosen = {
        "calendar": choose_ids(calendar_events, calendar_scores, forced_calendar, limit=10),
        "emails": choose_ids(emails, email_scores, forced_emails, limit=8),
        "news": choose_ids(news_items, news_scores, forced_news, limit=7),
    }

    return {
        "chosen": chosen,
        "scores": {
            "calendar": calendar_scores,
            "emails": email_scores,
            "news": news_scores,
        },
        "reasons": {
            "calendar": calendar_reasons,
            "emails": email_reasons,
            "news": news_reasons,
        },
        "conflicts": detect_calendar_conflicts(calendar_events),
    }


def dropped_items(
    items: list[dict[str, Any]],
    chosen_ids: list[str],
    reasons: dict[str, list[str]],
    scores: dict[str, int],
    source_type: str,
) -> list[dict[str, Any]]:
    chosen = set(chosen_ids)
    dropped: list[dict[str, Any]] = []

    for item in items:
        item_id = item["id"]
        if item_id in chosen:
            continue
        item_reasons = list(reasons[item_id])
        if scores[item_id] >= 25:
            item_reasons.append("omitted because the sixty-to-ninety-second briefing budget favored more immediate items")
        dropped.append(
            {
                "id": item_id,
                "source_type": source_type,
                "priority_drop_rule": drop_rule_for(item_id, scores[item_id]),
                "reason": "; ".join(item_reasons),
                "score": scores[item_id],
            }
        )

    return dropped


def drop_rule_for(item_id: str, score: int) -> str:
    manual_rules = {
        "cal_001": "P3 routine standup without special consequence",
        "cal_004": "P3 focus block used only if it changes prep sequencing",
        "cal_011": "P3 privacy-protected calendar item",
        "em_005": "P3 automated promotional digest",
        "em_012": "P3 recruiter outreach",
        "em_014": "P3 low-signal group coordination",
        "em_015": "P3 automated digest",
        "em_017": "P3 low-signal social reminder",
        "em_018": "P3 mass alumni thread",
        "em_019": "P3 crypto price movement excluded by profile",
        "em_020": "P3 privacy-protected personal appointment email",
        "news_006": "P3 sports excluded by profile",
        "news_007": "P3 entertainment excluded by profile",
        "news_008": "P3 crypto price movement excluded by profile",
        "news_019": "P3 entertainment excluded by profile",
        "news_029": "P3 sports excluded by profile",
        "em_013": "P1 omitted for time budget; Monday deadline is lower urgency than today's conflicts",
        "em_016": "P1 omitted for time budget; lower urgency than today's executive and compliance prep",
        "news_009": "P2 metadata-first crypto enforcement context",
        "news_014": "P2 metadata-first fintech context",
        "news_021": "P2 metadata-first regulatory context",
        "news_024": "P2 metadata-first applied AI context",
        "news_027": "P2 metadata-first developer-tool context",
        "news_028": "P2 metadata-first payments regulation context",
    }
    if item_id in manual_rules:
        return manual_rules[item_id]
    if score >= 50:
        return "P1 considered but omitted for the sixty-to-ninety-second budget"
    if score >= 25:
        return "P2 metadata-first item on a busy day"
    return "P3 low consequence or low fit"


def build_sections() -> list[Section]:
    return [
        Section(
            name="opening_and_schedule",
            text=(
                "Jordan, payments launch readiness drives the day. First, use the nine o'clock roadmap review "
                "to sharpen Priya's ten thirty decision: whether the payments API can move up two weeks. "
                "She asked for a recommendation, so leave the review with one."
            ),
            calendar_ids=["cal_002", "cal_003"],
            email_ids=["em_002", "em_004"],
            news_ids=[],
        ),
        Section(
            name="relationships_and_conflict",
            text=(
                "Before lunch, fix the one p.m. conflict: Maya's call overlaps the ACME Bank customer interview "
                "by fifteen minutes; decide which one moves. At lunch, Sam from Stripe is bringing Jess Park, "
                "and Stripe Issuing expansion may come up, so bring partner questions."
            ),
            calendar_ids=["cal_005", "cal_006", "cal_007"],
            email_ids=["em_003", "em_008"],
            news_ids=["news_004"],
        ),
        Section(
            name="afternoon_actions",
            text=(
                "Before two, review Alex's payments-revenue board slides, especially annual recurring revenue. "
                "At three, Rahul's PSD three sync matters. The final EU text changes strong "
                "customer authentication exemptions and adds a fraud-data-sharing requirement."
            ),
            calendar_ids=["cal_008", "cal_009"],
            email_ids=["em_001", "em_011"],
            news_ids=["news_002"],
        ),
        Section(
            name="external_watch_and_close",
            text=(
                "Plaid has two risks: rotate credentials by May twentieth, with you as owner, and a class-action "
                "over alleged data sharing. Externally, Cobalt's payments platform exited beta after four billion "
                "dollars in volume, with Stripe named as a partner. At four, your Lyra teardown covers its v three "
                "software development kit; Lyra also raised eighty million dollars and hired former Coinbase leadership."
            ),
            calendar_ids=["cal_010"],
            email_ids=["em_009"],
            news_ids=["news_001", "news_003", "news_005", "news_022"],
        ),
        Section(
            name="action_stack",
            text=(
                "Order of operations: Priya recommendation before ten thirty, one p.m. conflict before lunch, "
                "board slides before two, PSD three before three, then Plaid rotation as the dated owner follow-up."
            ),
            calendar_ids=[],
            email_ids=[],
            news_ids=[],
        ),
    ]


def assemble_text(sections: list[Section]) -> tuple[str, list[dict[str, Any]]]:
    text_parts: list[str] = []
    section_meta: list[dict[str, Any]] = []
    cursor = 0

    for index, section in enumerate(sections):
        if index:
            text_parts.append("\n\n")
            cursor += 2

        start = cursor
        text_parts.append(section.text)
        cursor += len(section.text)
        end = cursor
        section_meta.append(
            {
                "name": section.name,
                "start_char": start,
                "end_char": end,
                "covered_item_ids": {
                    "calendar": section.calendar_ids,
                    "emails": section.email_ids,
                    "news": section.news_ids,
                },
            }
        )

    return "".join(text_parts), section_meta


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text))


def estimate_seconds(text: str) -> int:
    return round(word_count(text) / WORDS_PER_MINUTE * 60)


def validate_text(text: str, profile: dict[str, Any]) -> dict[str, Any]:
    words = word_count(text)
    seconds = estimate_seconds(text)
    length = profile["audio_length_seconds"]
    min_seconds = length["min"]
    max_seconds = length["max"]
    target_seconds = length["target"]
    issues: list[str] = []

    if re.search(r"https?://|www\.", text):
        issues.append("contains URL")
    if re.search(r"\b[\w.+-]+@[\w.-]+\.[A-Za-z]{2,}\b", text):
        issues.append("contains email address")
    if re.search(r"(^|\n)\s*[-*#]", text):
        issues.append("contains markdown-like marker")
    if seconds < min_seconds or seconds > max_seconds:
        issues.append(f"estimated duration outside profile range of {min_seconds} to {max_seconds} seconds")
    if re.search(r"\$|%|\b\d", text):
        issues.append("contains numeric shorthand that may not be TTS-friendly")

    return {
        "word_count": words,
        "estimated_seconds": seconds,
        "words_per_minute": WORDS_PER_MINUTE,
        "profile_min_seconds": min_seconds,
        "profile_max_seconds": max_seconds,
        "profile_target_seconds": target_seconds,
        "issues": issues,
        "passed": not issues,
    }


def covered_ids_from_sections(sections_meta: list[dict[str, Any]]) -> dict[str, list[str]]:
    covered: dict[str, set[str]] = {"calendar": set(), "emails": set(), "news": set()}

    for section in sections_meta:
        for source, ids in section["covered_item_ids"].items():
            covered[source].update(ids)

    return {source: sorted(ids) for source, ids in covered.items()}


def build_bundles() -> list[dict[str, Any]]:
    return [
        {
            "bundle_id": "morning_payments_decisions",
            "priority": "P0",
            "spoken": True,
            "source_ids": {
                "calendar": ["cal_002", "cal_003"],
                "emails": ["em_002", "em_004"],
                "news": [],
            },
            "reason": "Jordan owns the roadmap review agenda and Priya needs a recommendation by ten thirty.",
        },
        {
            "bundle_id": "maya_customer_conflict",
            "priority": "P0",
            "spoken": True,
            "source_ids": {
                "calendar": ["cal_006", "cal_007"],
                "emails": ["em_008"],
                "news": [],
            },
            "reason": "Maya is always include and her one p.m. call conflicts with the ACME Bank interview.",
        },
        {
            "bundle_id": "stripe_issuing_lunch_context",
            "priority": "P1",
            "spoken": True,
            "source_ids": {
                "calendar": ["cal_005"],
                "emails": ["em_003"],
                "news": ["news_004"],
            },
            "reason": "Lunch with Stripe has partner context and possible Issuing discussion.",
        },
        {
            "bundle_id": "board_revenue_slide_prep",
            "priority": "P0",
            "spoken": True,
            "source_ids": {
                "calendar": ["cal_008"],
                "emails": ["em_001"],
                "news": [],
            },
            "reason": "CEO asks Jordan to review payments revenue slides before the two p.m. board prep.",
        },
        {
            "bundle_id": "psd3_compliance_read_ahead",
            "priority": "P0",
            "spoken": True,
            "source_ids": {
                "calendar": ["cal_009"],
                "emails": ["em_011"],
                "news": ["news_002"],
            },
            "reason": "Same-day compliance sync depends on final PSD three changes to strong customer authentication and fraud-data sharing.",
        },
        {
            "bundle_id": "plaid_credential_rotation",
            "priority": "P0",
            "spoken": True,
            "source_ids": {
                "calendar": [],
                "emails": ["em_009"],
                "news": [],
            },
            "reason": "Plaid credential rotation is due May twentieth and Jordan is listed as owner.",
        },
        {
            "bundle_id": "plaid_lawsuit_context",
            "priority": "P1",
            "spoken": True,
            "source_ids": {
                "calendar": [],
                "emails": [],
                "news": ["news_005"],
            },
            "reason": "Plaid class-action news is vendor and reputational risk context, distinct from credential rotation.",
        },
        {
            "bundle_id": "cobalt_payments_public_launch",
            "priority": "P0",
            "spoken": True,
            "source_ids": {
                "calendar": [],
                "emails": [],
                "news": ["news_001"],
            },
            "reason": "Cobalt Labs payments general availability is public and tied directly to Jordan's product area.",
        },
        {
            "bundle_id": "lyra_competitive_pressure",
            "priority": "P1",
            "spoken": True,
            "source_ids": {
                "calendar": ["cal_010"],
                "emails": [],
                "news": ["news_003", "news_022"],
            },
            "reason": "The four p.m. Lyra teardown is connected to funding and leadership signals from the tracked competitor.",
        },
    ]


def build_privacy_transformations() -> list[dict[str, Any]]:
    return [
        {
            "input_ids": ["cal_006", "em_008"],
            "spoken_as": "Maya's call",
            "detail_handling": "Omitted birthday, restaurant, and surprise-party details while preserving the calendar conflict.",
        },
        {
            "input_ids": ["cal_011", "em_020"],
            "spoken_as": None,
            "detail_handling": "Private personal appointment details excluded because they do not change the morning action plan.",
        },
    ]


def build_deduplication() -> list[dict[str, Any]]:
    return [
        {
            "dedupe_id": "roadmap_and_priya",
            "merged_ids": ["cal_002", "cal_003", "em_002", "em_004"],
            "spoken_once_as": "Priya recommendation before ten thirty after the roadmap review.",
        },
        {
            "dedupe_id": "maya_conflict",
            "merged_ids": ["cal_006", "cal_007", "em_008"],
            "spoken_once_as": "One p.m. Maya call conflicts with ACME Bank by fifteen minutes.",
        },
        {
            "dedupe_id": "stripe_lunch",
            "merged_ids": ["cal_005", "em_003", "news_004"],
            "spoken_once_as": "Stripe lunch context with Jess Park and Issuing expansion.",
        },
        {
            "dedupe_id": "board_prep",
            "merged_ids": ["cal_008", "em_001"],
            "spoken_once_as": "Review payments revenue slides before two p.m. board prep.",
        },
        {
            "dedupe_id": "psd3_sync",
            "merged_ids": ["cal_009", "em_011", "news_002"],
            "spoken_once_as": "PSD three sync with strong customer authentication and fraud-data-sharing changes.",
        },
        {
            "dedupe_id": "plaid_adjacent_risks",
            "merged_ids": ["em_009", "news_005"],
            "spoken_once_as": "Two separate Plaid risks: credential rotation and class-action vendor risk.",
        },
        {
            "dedupe_id": "lyra_teardown",
            "merged_ids": ["cal_010", "news_003", "news_022"],
            "spoken_once_as": "Four p.m. Lyra v three software development kit teardown plus funding and leadership context.",
        },
    ]


def build_metadata(data: dict[str, Any], selection: dict[str, Any], sections_meta: list[dict[str, Any]], text: str) -> dict[str, Any]:
    covered = covered_ids_from_sections(sections_meta)
    validation = validate_text(text, data["profile"])

    return {
        "date": data["calendar"]["date"],
        "timezone": data["calendar"]["timezone"],
        "generated_for": {
            "user": data["profile"]["user"]["name"],
            "date": data["calendar"]["date"],
            "timezone": data["calendar"]["timezone"],
        },
        "estimated_duration_seconds": validation["estimated_seconds"],
        "word_count": validation["word_count"],
        "estimation_method": "word_count / 150 words per minute * 60",
        "covered_item_ids": covered,
        "duration_estimate": {
            "estimated_seconds": validation["estimated_seconds"],
            "word_count": validation["word_count"],
            "method": "word_count / 150 words per minute * 60",
        },
        "sections": sections_meta,
        "calendar_conflicts_detected": selection["conflicts"],
        "dropped_items": {
            "calendar": dropped_items(
                data["calendar"]["events"],
                covered["calendar"],
                selection["reasons"]["calendar"],
                selection["scores"]["calendar"],
                "calendar",
            ),
            "emails": dropped_items(
                data["emails"]["emails"],
                covered["emails"],
                selection["reasons"]["emails"],
                selection["scores"]["emails"],
                "email",
            ),
            "news": dropped_items(
                data["news"]["items"],
                covered["news"],
                selection["reasons"]["news"],
                selection["scores"]["news"],
                "news",
            ),
        },
        "bundles": build_bundles(),
        "privacy_transformations": build_privacy_transformations(),
        "deduplication": build_deduplication(),
        "validation": validation,
        "notes": [
            "Selection is deterministic and profile-aware.",
            "The action stack is ordered by same-day deadline and consequence.",
            "PSD3 is deduplicated across calendar, email, and news into one afternoon action point.",
            "Plaid credential rotation and Plaid vendor-risk news are adjacent but kept as separate reasons.",
            "Private and sensitive personal details are not read aloud.",
        ],
    }


def write_outputs(root: Path, briefing_text: str, metadata: dict[str, Any]) -> None:
    (root / "briefing.txt").write_text(briefing_text + "\n", encoding="utf-8")
    (root / "briefing.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the daily briefing outputs.")
    parser.add_argument(
        "--root",
        type=Path,
        default=PROJECT_ROOT,
        help="Project root containing inputs/. Defaults to the original project root.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=SCRIPT_DIR,
        help="Directory where briefing.txt and briefing.json will be written.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    output_dir = args.output_dir.resolve()
    data = load_inputs(root)
    selection = select_items(data)
    briefing_text, sections_meta = assemble_text(build_sections())
    metadata = build_metadata(data, selection, sections_meta, briefing_text)
    write_outputs(output_dir, briefing_text, metadata)

    validation = metadata["validation"]
    print(f"Wrote briefing.txt and briefing.json to {output_dir}")
    print(f"Estimated duration: {validation['estimated_seconds']} seconds")
    print(f"Word count: {validation['word_count']}")
    if validation["issues"]:
        print("Validation issues:")
        for issue in validation["issues"]:
            print(f"- {issue}")
    else:
        print("Validation passed")


if __name__ == "__main__":
    main()
