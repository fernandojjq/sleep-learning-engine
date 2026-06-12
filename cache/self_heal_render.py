"""Self-healing render loop.

Memory budget on this Windows box is tight (~1.1 GB free out of 7.8 GB
total), so we try the encode in progressively cheaper configurations
until one completes. Each iteration: clean ffmpeg state, set the
encoder preset in the source file, set render_threads in the toml,
launch the CLI render, and poll for completion. Only return on
success or after all configurations are exhausted.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\proyectos\Proyectos Github\sleep_learning_engine")
SRC = ROOT / "src"
TOML = ROOT / ".sleep_learning_engine.toml"
BUILDER = ROOT / "src/sleep_learning_engine/video/builder.py"
LOG = ROOT / "logs/sleep_learning_engine.log"
RENDER_LOG = ROOT / "cache/render.out"
RENDER_ERR = ROOT / "cache/render.err"
CACHE = ROOT / "cache"
OUTPUT = ROOT / "output"
VENV_PY = ROOT / ".venv/Scripts/python.exe"

# (preset, threads, description)
TIERS = [
    ("veryfast", 2, "veryfast + 2 threads, 1080p"),
    ("superfast", 2, "superfast + 2 threads, 1080p"),
    ("ultrafast", 1, "ultrafast + 1 thread, 1080p"),
]

PRESET_MAP = {
    "veryfast": ("-preset", "veryfast", "-crf", "20", "-tune", "zerolatency"),
    "superfast": ("-preset", "superfast", "-crf", "20", "-tune", "zerolatency"),
    "ultrafast": ("-preset", "ultrafast", "-crf", "22", "-tune", "zerolatency"),
}


def patch_libx264(preset: str) -> None:
    flags_block = "(" + ", ".join(f'"{f}"' for f in PRESET_MAP[preset]) + ")"
    text = BUILDER.read_text(encoding="utf-8")
    # Match the libx264 HardwareChoice (with or without the comment) and
    # replace the flag tuple.
    pattern = re.compile(
        r'(libx264 = HardwareChoice\(\s*"libx264",\s*(?:\n\s*#[^\n]*\n)?\s*)\([^)]+\)',
        re.MULTILINE,
    )
    new_text, n = pattern.subn(rf'\1{flags_block}', text)
    if n == 0:
        # Fallback: replace the second occurrence (in the auto-fallback).
        # We do that by finding the literal flag tuple that starts with
        # ("-preset" and a libx264-style preset.
        pat2 = re.compile(
            r'\(""-preset"",\s*"(?:veryfast|superfast|ultrafast|medium|fast|slow)"\s*,[^)]+\)',
            re.MULTILINE,
        )
        new_text, n = pat2.subn(flags_block, text)
    if n == 0:
        raise RuntimeError("Could not patch libx264 preset in builder.py")
    BUILDER.write_text(new_text, encoding="utf-8")
    print(f"  [patch] libx264 preset -> {preset} (n={n})")


def patch_threads(threads: int) -> None:
    text = TOML.read_text(encoding="utf-8")
    new_text = re.sub(r"^render_threads\s*=\s*\d+", f"render_threads = {threads}", text, flags=re.MULTILINE)
    TOML.write_text(new_text, encoding="utf-8")
    print(f"  [patch] render_threads -> {threads}")


def clean_state() -> None:
    """Kill any lingering ffmpeg, truncate render log, remove partial MP4."""
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process ffmpeg,python -ErrorAction SilentlyContinue | "
         "Where-Object { $_.Path -like '*sleep_learning_engine*' -or $_.ProcessName -eq 'ffmpeg' } | "
         "ForEach-Object { Stop-Process -Id $_.Id -Force -ErrorAction SilentlyContinue }"],
        capture_output=True,
    )
    time.sleep(1)
    if RENDER_LOG.exists():
        RENDER_LOG.unlink()
    if RENDER_ERR.exists():
        RENDER_ERR.unlink()
    for mp4 in OUTPUT.glob("sleep_learning_engine-*.mp4"):
        if mp4.stat().st_size < 50_000_000:  # remove partial files
            print(f"  [clean] removing partial {mp4.name} ({mp4.stat().st_size} bytes)")
            mp4.unlink()


def launch_render(stem: str) -> int:
    env = os.environ.copy()
    env["TMP"] = str(CACHE / "tmp")
    env["TEMP"] = env["TMP"]
    (CACHE / "tmp").mkdir(parents=True, exist_ok=True)
    cmd = [
        str(VENV_PY), "-m", "sleep_learning_engine", "render",
        "--script", r"D:/Downloads/prueba.txt",
        "--output-stem", stem,
        "--json",
    ]
    print(f"  [launch] {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=open(RENDER_LOG, "wb"),
        stderr=open(RENDER_ERR, "wb"),
        env=env,
    )
    return proc.pid


def wait_for_done(pid: int, timeout: float) -> tuple[bool, str]:
    """Block until the process exits or timeout. Returns (ok, reason)."""
    start = time.time()
    last_size = -1
    stable_count = 0
    while time.time() - start < timeout:
        # Check if process is still alive.
        try:
            proc = subprocess.run(
                ["powershell", "-NoProfile", "-Command", f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue) -ne $null"],
                capture_output=True, text=True, timeout=5,
            )
            alive = "True" in proc.stdout
        except Exception:
            alive = True
        if not alive:
            return True, "process exited"
        # Check log for ffmpeg OOM/exit markers
        if LOG.exists():
            tail = LOG.read_text(encoding="utf-8", errors="ignore")[-2000:]
            if "Cannot allocate memory" in tail or "Error sending frames" in tail:
                return False, "ffmpeg OOM"
            if "Render failed" in tail and "exit code" in tail:
                return False, "ffmpeg errored"
        time.sleep(3)
    return False, f"timeout after {timeout}s"


def find_output(stem: str) -> Path | None:
    candidate = OUTPUT / f"{stem}.mp4"
    if candidate.exists() and candidate.stat().st_size > 100_000:
        return candidate
    return None


def main() -> int:
    print(f"Memory at start: {(int(subprocess.run(['powershell','-NoProfile','-Command','(Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory'], capture_output=True, text=True).stdout.strip()) or 0)/1e6:.2f} GB free")
    for tier_idx, (preset, threads, label) in enumerate(TIERS, start=1):
        print(f"\n=== Tier {tier_idx}/{len(TIERS)}: {label} ===")
        try:
            patch_libx264(preset)
            patch_threads(threads)
        except Exception as exc:
            print(f"  [skip] patch failed: {exc}")
            continue
        clean_state()
        stem = f"sleep_learning_engine-final-{time.strftime('%H%M%S')}"
        pid = launch_render(stem)
        ok, reason = wait_for_done(pid, timeout=900)
        if not ok:
            print(f"  [fail] {reason}")
            # Force-kill the python worker + any ffmpeg child
            subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 f"Get-Process -Id {pid} -ErrorAction SilentlyContinue | Stop-Process -Force; "
                 f"Get-Process ffmpeg -ErrorAction SilentlyContinue | Stop-Process -Force"],
                capture_output=True,
            )
            time.sleep(2)
            continue
        out = find_output(stem)
        if out:
            print(f"  [done] {out} ({out.stat().st_size/1e6:.1f} MB)")
            return 0
        else:
            print(f"  [fail] no output for stem {stem}")
    print("\nAll tiers exhausted. Check logs.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
