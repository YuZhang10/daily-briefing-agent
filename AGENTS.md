# AGENTS.md

This file gives Codex project-level context for the daily briefing agent repo.

## Project Context

- This is an agent-focused interview take-home.
- The goal is not only to make code run, but to show practical agent design judgment.
- Prefer concrete, inspectable artifacts over vague architecture talk.
- Keep important design decisions in `DECISIONS.md` as the project evolves.

## Source Material

- `README_RAW.md` is the original take-home prompt. Treat it as read-only source material and do not edit it.
- `inputs/*.json` are the original evaluation inputs. Do not mutate them for the submitted output.

## Daily Briefing Agent Principles

- Treat Jordan Chen as the current evaluation persona, not as hardcoded product logic.
- Optimize the briefing for a listener with no visual context.
- Prefer consequence-aware prioritization over source-by-source summarization.
- P0 items are things where delay, missing preparation, conflict, or ownership risk can cause real consequences.
- Calendar events that require no preparation can be briefly mentioned or omitted from audio.
- Calendar, email, and news items about the same real-world event should be merged into one spoken bundle while preserving all source IDs in metadata.
- Do not expose private or sensitive personal details in spoken output.
- Profile preferences must affect filtering, ranking, wording, and validation, not only prompt text.

## Implementation Preferences

- Keep the core briefing generator runnable without API keys or network access.
- Use deterministic policy for selection, filtering, privacy handling, deduplication, and metadata.
- LLM writers, online TTS, and other external services should be optional layers.
- Do not make online TTS the default, because briefing text can contain information derived from private calendar, email, and profile data.
- If an external service would receive user-derived content, call that out clearly and ask for explicit approval.
- `llm_runtime_workflow/` is the optional Gemini-backed runtime multi-agent service. Keep API keys in environment variables only.
- Avoid overengineering. This is expected to be a roughly two-hour prototype, so prefer a small, readable implementation with clear checks.

## Validation Commands

After changing core generation logic, run:

```bash
python3 vibe_coding_1_0/deterministic_baseline/generate_briefing.py
python3 multi_agent_workflow/outputs/review_repair_1/generate_briefing.py
```

For optional local audio variants, run:

```bash
.venv/bin/python vibe_coding_1_0/audio_preview/generate_audio_variants.py
```

The optional `--include-online` audio path may send briefing text to external TTS services and should not be used without explicit user approval.

For the optional Gemini multi-agent runtime, run only when external ModelHub access is approved:

```bash
python3 llm_runtime_workflow/run_gemini_workflow.py
```

## Documentation Expectations

- `README.md` is for human run instructions.
- `README_RAW.md` is the original prompt and should remain unchanged.
- `DECISIONS.md` is for architecture, trade-offs, AI usage notes, and known limitations.
- Write `DECISIONS.md` in the project owner's first-person voice. Avoid meta-evaluator phrasing such as "the interviewer would think", "if the interviewer mainly cares", or detached judge commentary.
- `briefing.json` should be generated metadata, not a hand-written explanation.
- If code behavior and documentation diverge, update both before calling the task done.
