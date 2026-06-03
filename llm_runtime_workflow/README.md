# LLM Runtime Workflow

This folder contains the optional Gemini-backed multi-agent service for the daily briefing agent. It keeps the deterministic v1 output intact and writes runtime LLM outputs into `outputs/`.

The service runs a real model-calling collaboration loop:

```text
PM Agent
  -> reads README_RAW.md, inputs/*.json, and local preflight signals
  -> writes SPEC.json and SPEC.md

Writer Agent
  -> writes briefing text and coverage claims from the PM spec

User Judge Agent
  -> reviews the candidate as Jordan using original inputs, spec, text, and metadata

Repair Agent
  -> rewrites once if validation or judge feedback requires it
```

## Safety

- Do not commit API keys.
- Set the API key through an environment variable.
- This workflow sends calendar, email, news, and profile-derived content to the configured ModelHub endpoint. Use it only when that data-sharing trade-off is acceptable.

## Run

From the project root:

```bash
python3 llm_runtime_workflow/run_gemini_workflow.py
```

The script auto-loads `.env` from the project root. Keep that file local; it is ignored by git.

Optional environment variables:

```bash
MODELHUB_BASE_URL=https://aidp-i18ntt-sg.tiktok-row.net
MODELHUB_MODEL=gemini-3.1-fl
MODELHUB_THINKING_BUDGET=0
MODELHUB_TIMEOUT_SECONDS=120
```

Useful options:

```bash
python3 llm_runtime_workflow/run_gemini_workflow.py --output-name gemini_multi_agent_2 --max-repair-rounds 2
```

Outputs go to:

```text
llm_runtime_workflow/outputs/gemini_multi_agent_1/
├── SPEC.md
├── SPEC.json
├── briefing.txt
├── briefing.json
├── review.md
├── review_report.json
├── run_summary.md
├── trace.json
├── run_config.json
├── local_preflight_signals.json
├── rounds/
└── agent_outputs/
```

## Prompt Files

- `prompts/01_pm_agent.md`
- `prompts/02_writer_agent.md`
- `prompts/03_user_judge_agent.md`
- `prompts/04_repair_agent.md`

## Why This Exists

The deterministic root generator is the safe five-minute fallback. This runtime path demonstrates the agent design more explicitly: multiple model-backed roles, structured handoffs, deterministic validation, and durable traces for review.
