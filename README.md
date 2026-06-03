# Daily Briefing Agent

This is a small, end-to-end prototype for generating a personalized morning audio briefing from the supplied JSON inputs.

The agent reads:

- `inputs/profile.json`
- `inputs/calendar.json`
- `inputs/emails.json`
- `inputs/news.json`

and writes versioned outputs under the selected workflow folder:

- `briefing.txt` - plain English text for TTS
- `briefing.json` - structured metadata explaining coverage, duration, sections, conflicts, and dropped items

## Quick Start

The recommended no-API local version is the v2 repaired generator:

```bash
python3 multi_agent_workflow/outputs/review_repair_1/generate_briefing.py
```

Expected output:

```text
Wrote briefing.txt and briefing.json to .../multi_agent_workflow/outputs/review_repair_1
Estimated duration: 84 seconds
Word count: 211
Validation passed
```

Outputs are written to:

```text
multi_agent_workflow/outputs/review_repair_1/briefing.txt
multi_agent_workflow/outputs/review_repair_1/briefing.json
```

## What The Agent Does

The no-API generator is a deterministic, profile-aware agent pipeline:

```text
Ingest JSON
  -> score calendar, email, and news items
  -> detect private items and calendar conflicts
  -> deduplicate repeated themes
  -> build a compact briefing plan
  -> write TTS-friendly briefing text
  -> validate duration and formatting
  -> write metadata
```

I kept the local path dependency-free so the project can still run quickly without API keys. The original v1.0 deterministic baseline is preserved under `vibe_coding_1_0/deterministic_baseline/`; the v2 repaired generator is the stronger low-latency local candidate.

## Vibe Coding 1.0 Archive

The original v1.0 code and generated outputs are archived together:

```bash
python3 vibe_coding_1_0/deterministic_baseline/generate_briefing.py
```

Outputs are written to:

```text
vibe_coding_1_0/deterministic_baseline/briefing.txt
vibe_coding_1_0/deterministic_baseline/briefing.json
```

## Optional Gemini Multi-Agent Runtime

There is also an optional runtime LLM service under `llm_runtime_workflow/`. It uses a real ModelHub/Gemini-compatible endpoint and runs a PM -> Writer -> User Judge -> optional Repair loop.

```bash
python3 llm_runtime_workflow/run_gemini_workflow.py
```

That workflow sends profile, calendar, email, and news-derived content to the configured endpoint. The script auto-loads `.env` from the project root; keep that file local and do not commit it.

Outputs are written to:

```text
llm_runtime_workflow/outputs/gemini_multi_agent_1/
```

## Output Quality Checks

The generators validate that `briefing.txt`:

- stays within the target sixty-to-ninety-second window using a one-hundred-fifty-words-per-minute estimate;
- has no URLs or email addresses;
- has no Markdown-style bullets or headings;
- avoids numeric shorthand such as dollar signs, percent signs, or raw digits.

The current recommended no-API output is two hundred eleven words, estimated at eighty-four seconds.

## Optional Audio Preview

The core task does not require audio output, but the v1.0 archive includes an optional local TTS preview script.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r vibe_coding_1_0/audio_preview/requirements.txt
.venv/bin/python vibe_coding_1_0/audio_preview/generate_audio_variants.py
```

This reads `vibe_coding_1_0/deterministic_baseline/briefing.txt` and writes local system-voice previews under `vibe_coding_1_0/audio_preview/audio/`:

```text
vibe_coding_1_0/audio_preview/audio/briefing_local_samantha_165wpm.mp3
vibe_coding_1_0/audio_preview/audio/briefing_local_daniel_160wpm.mp3
vibe_coding_1_0/audio_preview/audio/briefing_local_karen_160wpm.mp3
vibe_coding_1_0/audio_preview/audio/audio_manifest.json
```

The default audio path does not send briefing text to online TTS services. The optional `--include-online` flag can try `edge-tts` and `gTTS`, but that sends briefing text derived from calendar, email, and profile data to external services, so do not use it unless that data-sharing trade-off is acceptable.

## Files

```text
.
├── AGENTS.md
├── README_RAW.md
├── llm_runtime_workflow/
├── multi_agent_workflow/
│   └── outputs/
│       └── review_repair_1/
│           ├── generate_briefing.py
│           ├── briefing.txt
│           └── briefing.json
├── vibe_coding_1_0/
│   ├── deterministic_baseline/
│   │   ├── generate_briefing.py
│   │   ├── briefing.txt
│   │   └── briefing.json
│   └── audio_preview/
│       ├── requirements.txt
│       ├── generate_audio_variants.py
│       └── audio/
├── DECISIONS.md
├── DECISIONS.template.md
└── inputs/
    ├── profile.json
    ├── calendar.json
    ├── emails.json
    └── news.json
```

## Design Notes

See `DECISIONS.md` for:

- architecture diagram;
- selection and ranking policy;
- how profile preferences are enforced;
- how PSD3 and other repeated themes are deduplicated;
- why certain relevant items were dropped;
- AI tool usage notes and known limitations.
