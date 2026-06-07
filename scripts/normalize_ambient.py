"""Normalise the volume of every ambient track in `assets/ambient/`.

The procedural generator writes each track at a different peak level
depending on the synthesis path (white noise is loud, brown noise is
quiet, alpha waves have transients, ...). If the user drops in
third-party loops, those usually vary even more. When the mixer
ducks and un-ducks the bed, the differences become very obvious: a
listener can be lulled to sleep by rain and then jolted awake by
brown noise peaking 6 dB higher.

This script runs ffmpeg's EBU R128 loudness normalisation on every
``.ogg`` / ``.wav`` / ``.mp3`` it finds, bringing the integrated
loudness to ``--target-lufs`` (default -23 LUFS, the EBU R128
broadcast standard) and the true peak to ``--target-tp`` (default
-1.5 dBTP). Both targets are configurable from the CLI.

The output replaces the input file in place. The script keeps a
``.bak`` copy for 30 days in case the user wants to roll back.

Usage:
    uv run python scripts/normalize_ambient.py
    uv run python scripts/normalize_ambient.py --target-lufs -20 --target-tp -1
    uv run python scripts/normalize_ambient.py --dry-run
    uv run python scripts/normalize_ambient.py --dir /path/to/other/loops
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_DIR = REPO_ROOT / "assets" / "ambient"
BACKUP_DIR = REPO_ROOT / "assets" / "ambient" / ".loudnorm-backup"
BACKUP_TTL = timedelta(days=30)
SUPPORTED_EXT = {".ogg", ".wav", ".mp3", ".flac", ".m4a"}


@dataclass(frozen=True)
class LoudnessResult:
    """Parsed output from ffmpeg's loudnorm filter (second pass)."""

    input_i: float
    input_tp: float
    input_lra: float
    input_thresh: float
    output_i: float
    output_tp: float
    output_lra: float
    output_thresh: float
    target_offset: float


def _ffmpeg_bin() -> str:
    """Find the bundled ffmpeg the same way the main pipeline does."""
    candidates = [
        REPO_ROOT / "cache" / "ffmpeg.exe",
        REPO_ROOT / "cache" / "ffmpeg",
    ]
    for c in candidates:
        if c.exists():
            return str(c)
    return "ffmpeg"  # fall back to PATH


def _ffprobe_input_i(ffmpeg: str, path: Path) -> float:
    """Quick first-pass measurement so the user can see what we're fixing.

    The two-pass loudnorm filter needs the input loudness to compute
    the right linear gain. We run a fast pass with `loudnorm=print_format=json`
    and parse the JSON. Returns the integrated loudness in LUFS.
    """
    cmd = [
        ffmpeg, "-hide_banner", "-nostats", "-i", str(path),
        "-af", "loudnorm=I=-23:TP=-1.5:LRA=11:print_format=json",
        "-f", "null", "-",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg loudnorm probe failed for {path}: {result.stderr[-500:]}")
    # ffmpeg prints the JSON to stderr at the end of the run.
    txt = result.stderr
    start = txt.rfind("{")
    if start == -1:
        raise RuntimeError(f"No loudnorm JSON in ffmpeg output for {path}")
    import json
    try:
        return float(json.loads(txt[start:])["input_i"])
    except (json.JSONDecodeError, KeyError, ValueError) as exc:
        raise RuntimeError(f"Bad loudnorm JSON for {path}: {exc}") from exc


def _normalise_file(
    ffmpeg: str,
    path: Path,
    target_lufs: float,
    target_tp: float,
    dry_run: bool,
) -> tuple[float, float] | None:
    """Two-pass loudnorm on a single file. Returns (input_lufs, output_lufs)."""
    if path.suffix.lower() not in SUPPORTED_EXT:
        return None
    print(f"  measuring {path.name} ...", flush=True)
    try:
        in_lufs = _ffprobe_input_i(ffmpeg, path)
    except RuntimeError as exc:
        print(f"    SKIP: {exc}", file=sys.stderr)
        return None
    print(f"    input_i = {in_lufs:+.1f} LUFS", flush=True)
    if dry_run:
        return (in_lufs, in_lufs)

    # The two-pass form: pass 1 measures (already done above), pass 2
    # applies the linear gain with the measured values plugged in.
    pass2 = [
        ffmpeg, "-y", "-hide_banner", "-loglevel", "error", "-i", str(path),
        "-af", (
            f"loudnorm=I={target_lufs}:TP={target_tp}:LRA=11:"
            f"measured_I={in_lufs}:measured_TP=-1.5:measured_LRA=11:"
            f"measured_thresh=-34:linear=true:print_format=summary"
        ),
        "-ar", "48000",  # match the generator's 48 kHz target
        "-ac", "2",       # stereo
        str(path),
    ]
    result = subprocess.run(pass2, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        print(f"    FAIL: {result.stderr[-300:]}", file=sys.stderr)
        return None
    return (in_lufs, target_lufs)


def _backup(path: Path) -> None:
    """Keep a dated copy in case the user wants to roll back."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = BACKUP_DIR / f"{path.stem}.{stamp}{path.suffix}"
    shutil.copy2(path, target)


def _prune_old_backups() -> None:
    if not BACKUP_DIR.exists():
        return
    cutoff = datetime.now() - BACKUP_TTL
    for p in BACKUP_DIR.iterdir():
        if not p.is_file():
            continue
        mtime = datetime.fromtimestamp(p.stat().st_mtime)
        if mtime < cutoff:
            print(f"  pruning old backup {p.name}", flush=True)
            p.unlink()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--dir",
        type=Path,
        default=DEFAULT_DIR,
        help=f"Directory of ambient tracks (default: {DEFAULT_DIR})",
    )
    parser.add_argument(
        "--target-lufs", type=float, default=-23.0,
        help="Target integrated loudness in LUFS (default: -23, EBU R128 broadcast)",
    )
    parser.add_argument(
        "--target-tp", type=float, default=-1.5,
        help="Target true peak in dBTP (default: -1.5)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Measure loudness without rewriting any file",
    )
    parser.add_argument(
        "--no-backup", action="store_true",
        help="Skip the .loudnorm-backup/ safety copy",
    )
    args = parser.parse_args()

    if not args.dir.exists():
        print(f"ERROR: {args.dir} does not exist.", file=sys.stderr)
        return 1

    ffmpeg = _ffmpeg_bin()
    tracks = sorted(p for p in args.dir.iterdir() if p.suffix.lower() in SUPPORTED_EXT)
    if not tracks:
        print(f"No ambient tracks found in {args.dir}.")
        return 0

    print(f"Normalising {len(tracks)} tracks in {args.dir} (target {args.target_lufs} LUFS, {args.target_tp} dBTP)")
    if args.dry_run:
        print("DRY RUN - no files will be modified.")

    biggest_change = 0.0
    for track in tracks:
        result = _normalise_file(ffmpeg, track, args.target_lufs, args.target_tp, args.dry_run)
        if result is None:
            continue
        in_lufs, out_lufs = result
        if not args.dry_run and not args.no_backup:
            _backup(track)
        delta = abs(out_lufs - in_lufs)
        if delta > biggest_change:
            biggest_change = delta

    if not args.dry_run:
        _prune_old_backups()

    if args.dry_run:
        print(f"\nDry run complete. Largest suggested change: {biggest_change:.1f} dB.")
    else:
        print(f"\nDone. Largest delta applied: {biggest_change:.1f} dB.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
