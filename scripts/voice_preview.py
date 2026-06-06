"""Generate voice previews so you can pick your favourite English narrator.

Renders 10-second samples of the curated voice set with the recommended
sleep settings (rate -10%, pitch -2Hz). Output goes to
``output/voice-previews/`` as one MP3 per voice plus a manifest.

Usage:
    uv run python scripts/voice_preview.py
    uv run python scripts/voice_preview.py --voice en-US-AriaNeural
    uv run python scripts/voice_preview.py --text "Your custom preview sentence."
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

import edge_tts  # type: ignore[import-not-found]

# --------------------------------------------------------------------- data

DEFAULT_SAMPLE_TEXT = (
    "Take a slow breath in, and let it go. Imagine a quiet room where the "
    "only sound is the gentle rhythm of your own breathing. Tonight, we "
    "explore the history of ancient Rome, one peaceful thought at a time."
)

# Hand-picked English voices, sorted by category. Each entry is
# (voice_id, one-line description, recommended_rate).
VOICES: tuple[tuple[str, str, str], ...] = (
    # Warm female narrators (most popular for sleep content).
    ("en-US-AriaNeural", "Warm, conversational, mid-range female", "-10%"),
    ("en-US-EmmaNeural", "Soft, calm, slightly breathy female", "-12%"),
    ("en-US-JennyNeural", "Friendly, clear, energetic female", "-8%"),
    ("en-US-MichelleNeural", "Young, bright female", "-10%"),
    ("en-US-SaraNeural", "Young, casual female", "-10%"),
    # Mature female narrators.
    ("en-US-JaneNeural", "Mature, calm, slightly formal female", "-12%"),
    ("en-US-NancyNeural", "Mature, warm, audio-book feel", "-10%"),
    # Male narrators.
    ("en-US-GuyNeural", "Casual, warm, mid-range male", "-10%"),
    ("en-US-DavisNeural", "Professional, clear, slightly deep male", "-10%"),
    ("en-US-TonyNeural", "Casual, younger male", "-10%"),
    ("en-US-AndrewNeural", "Mature, calm, audiobook-style male", "-12%"),
    ("en-US-BrianNeural", "Deep, resonant, very calming male", "-10%"),
    ("en-US-RogerNeural", "Older, dignified male", "-10%"),
    # British voices.
    ("en-GB-SoniaNeural", "Mature British female, very polished", "-10%"),
    ("en-GB-RyanNeural", "Warm British male, audiobook feel", "-10%"),
    ("en-GB-LibbyNeural", "Young British female", "-10%"),
    ("en-GB-ThomasNeural", "Mature British male, deep", "-12%"),
    # Other English dialects.
    ("en-AU-NatashaNeural", "Calm Australian female", "-10%"),
    ("en-AU-WilliamNeural", "Mature Australian male", "-10%"),
    ("en-CA-ClaraNeural", "Calm Canadian female", "-10%"),
    ("en-IN-NeerjaNeural", "Soft Indian-accent female", "-10%"),
    ("en-IE-EmilyNeural", "Soft Irish-accent female", "-10%"),
)


# --------------------------------------------------------------------- render


async def _render_one(voice: str, text: str, rate: str, out: Path) -> float:
    """Render a single preview and return its duration in seconds."""
    comm = edge_tts.Communicate(text=text, voice=voice, rate=rate, pitch="-2Hz")
    await comm.save(str(out))
    if not out.exists() or out.stat().st_size == 0:
        raise RuntimeError(f"edge-tts produced no audio for {voice}")
    return _probe_duration(out)


def _probe_duration(path: Path) -> float:
    import subprocess

    ffprobe = ROOT / "cache" / ("ffprobe.exe" if sys.platform.startswith("win") else "ffprobe")
    if not ffprobe.exists():
        ffprobe = Path("ffprobe")
    try:
        result = subprocess.run(
            [
                str(ffprobe),
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return float(result.stdout.strip() or "0")
    except Exception:  # noqa: BLE001
        return 0.0


async def _render_all(text: str, only: str | None) -> list[tuple[str, Path, float, str]]:
    out_dir = ROOT / "output" / "voice-previews"
    out_dir.mkdir(parents=True, exist_ok=True)
    results: list[tuple[str, Path, float, str]] = []
    for voice, desc, rate in VOICES:
        if only and voice != only:
            continue
        slug = voice.replace("-", "_").lower()
        out = out_dir / f"{slug}.mp3"
        try:
            duration = await _render_one(voice, text, rate, out)
        except Exception as exc:  # noqa: BLE001
            print(f"  SKIP {voice:30s}  ({exc.__class__.__name__})")
            continue
        # Drop zero-byte files (the request succeeded but produced silence).
        if out.stat().st_size < 1024:
            print(f"  SKIP {voice:30s}  (empty output)")
            out.unlink(missing_ok=True)
            continue
        print(f"  ok  {voice:30s}  {duration:5.1f}s  -> {out.name}")
        results.append((voice, out, duration, desc))
    return results


def _write_manifest(results: list[tuple[str, Path, float, str]]) -> Path:
    out_dir = ROOT / "output" / "voice-previews"
    manifest = out_dir / "manifest.csv"
    with manifest.open("w", encoding="utf-8") as fh:
        fh.write("voice,file,duration_seconds,description\n")
        for voice, path, duration, desc in results:
            fh.write(f"{voice},{path.name},{duration:.2f},{desc}\n")
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--voice",
        help="Render a single voice by id (e.g. en-US-AriaNeural).",
    )
    parser.add_argument(
        "--text",
        default=DEFAULT_SAMPLE_TEXT,
        help="The sample sentence each voice will read.",
    )
    args = parser.parse_args()

    results = asyncio.run(_render_all(args.text, args.voice))
    if results:
        manifest = _write_manifest(results)
        print(f"\nManifest: {manifest}")
        print("Open any of the MP3 files in your music player to compare.")
    return 0 if results else 1


if __name__ == "__main__":
    raise SystemExit(main())
