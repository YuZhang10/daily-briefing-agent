#!/usr/bin/env python3
"""Generate optional audio variants for listening tests.

The core briefing generator is dependency-free. This script is intentionally
separate because audio generation uses optional TTS packages and, for two
variants, network-backed services.
"""

from __future__ import annotations

import asyncio
import argparse
import json
import shutil
import subprocess
import traceback
from pathlib import Path
from typing import Callable


SCRIPT_ROOT = Path(__file__).resolve().parent
V1_ROOT = SCRIPT_ROOT.parent
TEXT_PATH = V1_ROOT / "deterministic_baseline" / "briefing.txt"
AUDIO_DIR = SCRIPT_ROOT / "audio"
MANIFEST_PATH = AUDIO_DIR / "audio_manifest.json"


def read_text() -> str:
    return TEXT_PATH.read_text(encoding="utf-8").strip()


def file_info(path: Path) -> dict[str, object]:
    if not path.exists():
        return {"path": str(path.relative_to(SCRIPT_ROOT)), "exists": False, "bytes": 0}
    return {
        "path": str(path.relative_to(SCRIPT_ROOT)),
        "exists": True,
        "bytes": path.stat().st_size,
    }


def convert_to_mp3(input_path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return input_path

    output_path = input_path.with_suffix(".mp3")
    subprocess.run(
        [
            ffmpeg,
            "-y",
            "-i",
            str(input_path),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            "128k",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return output_path


async def generate_edge_tts(text: str) -> Path:
    import edge_tts

    output = AUDIO_DIR / "briefing_edge_jenny.mp3"
    communicate = edge_tts.Communicate(
        text=text,
        voice="en-US-JennyNeural",
        rate="-8%",
        volume="+0%",
    )
    await communicate.save(str(output))
    return output


def generate_gtts(text: str) -> Path:
    from gtts import gTTS

    output = AUDIO_DIR / "briefing_gtts_us.mp3"
    tts = gTTS(text=text, lang="en", tld="com", slow=False)
    tts.save(str(output))
    return output


def generate_pyttsx3_variant(text: str, name: str, voice_hint: str, rate: int) -> Path:
    import pyttsx3

    output = AUDIO_DIR / f"briefing_local_{name}.aiff"
    engine = pyttsx3.init()
    engine.setProperty("rate", rate)

    for voice in engine.getProperty("voices"):
        voice_name = getattr(voice, "name", "")
        voice_id = getattr(voice, "id", "")
        if voice_hint in voice_name or voice_hint in voice_id:
            engine.setProperty("voice", voice_id)
            break

    engine.save_to_file(text, str(output))
    engine.runAndWait()
    return convert_to_mp3(output)


def generate_local_samantha(text: str) -> Path:
    return generate_pyttsx3_variant(text, "samantha_165wpm", "Samantha", 165)


def generate_local_daniel(text: str) -> Path:
    return generate_pyttsx3_variant(text, "daniel_160wpm", "Daniel", 160)


def generate_local_karen(text: str) -> Path:
    return generate_pyttsx3_variant(text, "karen_160wpm", "Karen", 160)


def run_sync_variant(name: str, fn: Callable[[str], Path], text: str) -> dict[str, object]:
    try:
        output = fn(text)
        return {"name": name, "status": "ok", **file_info(output)}
    except Exception as exc:  # pragma: no cover - listening utility
        return {
            "name": name,
            "status": "error",
            "error": str(exc),
            "traceback": traceback.format_exc(),
        }


async def main() -> None:
    parser = argparse.ArgumentParser(description="Generate audio variants for briefing.txt.")
    parser.add_argument(
        "--include-online",
        action="store_true",
        help="Also try edge-tts and gTTS. This sends briefing text to external online TTS services.",
    )
    args = parser.parse_args()

    AUDIO_DIR.mkdir(exist_ok=True)
    text = read_text()
    results: list[dict[str, object]] = []

    local_variants: list[tuple[str, Callable[[str], Path]]] = [
        ("local-samantha-165wpm", generate_local_samantha),
        ("local-daniel-160wpm", generate_local_daniel),
        ("local-karen-160wpm", generate_local_karen),
    ]
    for name, fn in local_variants:
        results.append(run_sync_variant(name, fn, text))

    if args.include_online:
        try:
            edge_output = await generate_edge_tts(text)
            results.append({"name": "edge-tts-jenny", "status": "ok", **file_info(edge_output)})
        except Exception as exc:  # pragma: no cover - listening utility
            results.append(
                {
                    "name": "edge-tts-jenny",
                    "status": "error",
                    "error": str(exc),
                    "traceback": traceback.format_exc(),
                }
            )

        results.append(run_sync_variant("gtts-us", generate_gtts, text))

    MANIFEST_PATH.write_text(json.dumps({"results": results}, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote manifest: {MANIFEST_PATH.relative_to(SCRIPT_ROOT)}")
    for result in results:
        if result["status"] == "ok":
            print(f"{result['name']}: {result['path']} ({result['bytes']} bytes)")
        else:
            print(f"{result['name']}: ERROR - {result['error']}")


if __name__ == "__main__":
    asyncio.run(main())
