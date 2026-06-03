# Multi-Agent Workflow Draft

This folder defines a draft multi-agent collaboration loop for improving the daily briefing agent. It is not executed automatically yet. The goal is to make each agent role explicit before running the workflow.

## Roles

```text
PM Agent
  -> extracts product requirements and acceptance criteria
  -> writes artifacts/SPEC.md and artifacts/priority_policy.json

Engineer Agent
  -> implements or revises the generator from PM requirements and review feedback
  -> writes a variant under outputs/ rather than overwriting the v1.0 root output

User Judge Agent
  -> acts as Jordan, the listener
  -> reviews inputs plus briefing.txt/briefing.json
  -> writes artifacts/REVIEW.md and artifacts/review_report.json
```

## Intended Loop

```text
Round 1:
  Run PM Agent
  Produce SPEC.md and priority_policy.json

Round 2:
  Run Engineer Agent
  Produce outputs/review_repair_1/generate_briefing.py, briefing.txt, briefing.json, and NOTES.md

Round 3:
  Run User Judge Agent
  Produce REVIEW.md and review_report.json for the selected output target

Round 4:
  Run Engineer Agent again using the review feedback

Round 5:
  Run User Judge Agent again for acceptance
```

## Stop Criteria

Stop the review-repair loop when:

- deterministic validation passes;
- the User Judge has no P0 findings;
- the User Judge has at most one unresolved P1 finding;
- remaining issues are P2 polish or subjective taste;
- the loop has run two review-repair cycles unless the human asks to continue.

The goal is not to chase endless minor wording preferences. The loop should stop once the briefing is useful, safe, faithful to the inputs, and inside the time budget.

## Audio Boundary

The first version of this workflow does not give the User Judge real audio-listening ability. The judge reviews TTS friendliness from `briefing.txt` and duration/metadata from `briefing.json`.

Human listener feedback overrides the judge on voice quality, pacing feel, and preferred audio preview.

## Guardrails

- Do not edit `README_RAW.md`; it is original source material.
- Do not mutate `inputs/*.json` for submitted outputs.
- Keep core generation runnable without API keys or network access.
- Treat online LLM/TTS services as optional because the data is derived from calendar, email, and profile content.
- Prefer durable file handoffs over hidden chat-only reasoning.

## Prompt Files

- `prompts/01_pm_agent.md`
- `prompts/02_engineer_agent.md`
- `prompts/03_user_judge_agent.md`
- `prompts/04_orchestrator.md`

## Artifact Targets

- `artifacts/SPEC.md`
- `artifacts/priority_policy.json`
- `artifacts/REVIEW.md`
- `artifacts/review_report.json`
- `outputs/review_repair_1/generate_briefing.py`
- `outputs/review_repair_1/briefing.txt`
- `outputs/review_repair_1/briefing.json`
- `outputs/review_repair_1/NOTES.md`
