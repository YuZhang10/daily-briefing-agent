# Vibe Coding 1.0

This folder preserves the first runnable local version and its audio preview artifacts.

## Deterministic Baseline

Run from the project root:

```bash
python3 vibe_coding_1_0/deterministic_baseline/generate_briefing.py
```

Outputs:

```text
vibe_coding_1_0/deterministic_baseline/briefing.txt
vibe_coding_1_0/deterministic_baseline/briefing.json
```

## Audio Preview

Run from the project root after creating the optional virtual environment:

```bash
.venv/bin/python -m pip install -r vibe_coding_1_0/audio_preview/requirements.txt
.venv/bin/python vibe_coding_1_0/audio_preview/generate_audio_variants.py
```

The audio script reads `vibe_coding_1_0/deterministic_baseline/briefing.txt` and writes MP3 previews under `vibe_coding_1_0/audio_preview/audio/`.
