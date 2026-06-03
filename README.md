# Daily Briefing Agent

This is a small, end-to-end prototype for generating a personalized morning audio briefing from the supplied JSON inputs.

The agent reads:

- `inputs/profile.json`
- `inputs/calendar.json`
- `inputs/emails.json`
- `inputs/news.json`

and writes:

- `briefing.txt` - plain English text for TTS
- `briefing.json` - structured metadata explaining coverage, duration, sections, conflicts, and dropped items

## Quick Start

No external dependencies are required.

```bash
python3 generate_briefing.py
```

Expected output:

```text
Wrote briefing.txt and briefing.json
Estimated duration: 85 seconds
Word count: 212
Validation passed
```

## What The Agent Does

The implementation is a deterministic, profile-aware agent pipeline:

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

I kept the first version dependency-free so reviewers can run it in five minutes without API keys. The writer step is isolated in `generate_briefing.py`, so it can be replaced with an LLM writer later while keeping deterministic selection, privacy filtering, and metadata generation.

## Output Quality Checks

The script validates that `briefing.txt`:

- stays within the target sixty-to-ninety-second window using a one-hundred-fifty-words-per-minute estimate;
- has no URLs or email addresses;
- has no Markdown-style bullets or headings;
- avoids numeric shorthand such as dollar signs, percent signs, or raw digits.

The current generated briefing is two hundred twelve words, estimated at eighty-five seconds.

## Optional Audio Preview

The core task does not require audio output, but this repo includes an optional local TTS preview script.

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python generate_audio_variants.py
```

This writes local system-voice previews under `audio/`:

```text
audio/briefing_local_samantha_165wpm.mp3
audio/briefing_local_daniel_160wpm.mp3
audio/briefing_local_karen_160wpm.mp3
audio/audio_manifest.json
```

The default audio path does not send briefing text to online TTS services. The optional `--include-online` flag can try `edge-tts` and `gTTS`, but that sends briefing text derived from calendar, email, and profile data to external services, so do not use it unless that data-sharing trade-off is acceptable.

## Files

```text
.
├── generate_briefing.py
├── generate_audio_variants.py
├── requirements.txt
├── briefing.txt
├── briefing.json
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
