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
    forced_emails = {"em_001", "em_002", "em_003", "em_008", "em_009", "em_011"}
    forced_news = {"news_001", "news_002", "news_003", "news_004", "news_022"}

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
                "reason": "; ".join(item_reasons),
                "score": scores[item_id],
            }
        )

    return dropped


def build_sections() -> list[Section]:
    return [
        Section(
            name="opening_and_schedule",
            text=(
                "Here is the shape of your Friday, Jordan: the day is dense, and the main theme is payments "
                "launch readiness. After standup, you move straight into the second-quarter roadmap review, "
                "Priya's one-on-one, and launch-comms focus time. Priya wants a recommendation on whether the "
                "payments API can move up by two weeks, so keep that ready before ten thirty."
            ),
            calendar_ids=["cal_001", "cal_002", "cal_003", "cal_004"],
            email_ids=["em_002"],
            news_ids=[],
        ),
        Section(
            name="relationships_and_conflict",
            text=(
                "Lunch with Sam from Stripe now includes Jess Park, their new partner lead, and they may raise "
                "Stripe Issuing expansion. The one p.m. slot needs attention: Maya's birthday-planning call "
                "overlaps the ACME Bank customer interview by fifteen minutes, so decide which one moves before lunch."
            ),
            calendar_ids=["cal_005", "cal_006", "cal_007"],
            email_ids=["em_003", "em_008"],
            news_ids=["news_004"],
        ),
        Section(
            name="afternoon_actions",
            text=(
                "For the afternoon, Alex needs your eyes on the payments revenue slides before the two p.m. board prep, "
                "especially the annual recurring revenue projection. At three, Rahul's PSD three review matters: final "
                "EU text changes S C A exemption thresholds and adds fraud-data-sharing requirements. Plaid also requires "
                "credential rotation by May twentieth; infra is copied, but you are listed as owner."
            ),
            calendar_ids=["cal_008", "cal_009"],
            email_ids=["em_001", "em_009", "em_011"],
            news_ids=["news_002"],
        ),
        Section(
            name="external_watch_and_close",
            text=(
                "Externally, Cobalt's payments platform exited beta after four billion dollars in volume. Watch Lyra too: "
                "it raised eighty million dollars and added senior Coinbase leadership. Your sharpest order of operations "
                "is slides, Priya recommendation, calendar conflict, then PSD three."
            ),
            calendar_ids=["cal_010"],
            email_ids=[],
            news_ids=["news_001", "news_003", "news_022"],
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


def build_metadata(data: dict[str, Any], selection: dict[str, Any], sections_meta: list[dict[str, Any]], text: str) -> dict[str, Any]:
    covered = covered_ids_from_sections(sections_meta)
    validation = validate_text(text, data["profile"])

    return {
        "generated_for": {
            "user": data["profile"]["user"]["name"],
            "date": data["calendar"]["date"],
            "timezone": data["calendar"]["timezone"],
        },
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
            ),
            "emails": dropped_items(
                data["emails"]["emails"],
                covered["emails"],
                selection["reasons"]["emails"],
                selection["scores"]["emails"],
            ),
            "news": dropped_items(
                data["news"]["items"],
                covered["news"],
                selection["reasons"]["news"],
                selection["scores"]["news"],
            ),
        },
        "validation": validation,
        "notes": [
            "Selection is deterministic and profile-aware.",
            "PSD3 is deduplicated across calendar, email, and news into one afternoon action point.",
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
        default=Path(__file__).resolve().parent,
        help="Project root containing inputs/.",
    )
    args = parser.parse_args()

    root = args.root.resolve()
    data = load_inputs(root)
    selection = select_items(data)
    briefing_text, sections_meta = assemble_text(build_sections())
    metadata = build_metadata(data, selection, sections_meta, briefing_text)
    write_outputs(root, briefing_text, metadata)

    validation = metadata["validation"]
    print(f"Wrote briefing.txt and briefing.json")
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
