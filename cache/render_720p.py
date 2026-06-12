"""Switch sleep_learning_engine to the most memory-frugal render config possible.

For a Windows box with ~1 GB free RAM at idle, we drop the encoder to
ultrafast (zerolatency tune), one thread, and 720p. The audio and the
script are untouched; only the final video resolution and the
encoder preset change.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(r"D:\proyectos\Proyectos Github\sleep_learning_engine")
TOML = ROOT / ".sleep_learning_engine.toml"
BUILDER = ROOT / "src/sleep_learning_engine/video/builder.py"
LOG = ROOT / "logs/sleep_learning_engine.log"
RENDER_OUT = ROOT / "cache/render.out"
RENDER_ERR = ROOT / "cache/render.err"
OUTPUT = ROOT / "output"
VENV_PY = ROOT / ".venv/Scripts/python.exe"
SCRIPT = r"D:/Downloads/prueba.txt"


def patch_toml_preset_720p() -> None:
    text = TOML.read_text(encoding="utf-8")
    new = text.replace('output_preset = "sleep_1080p"', 'output_preset = "sleep_720p"')
    new = new.replace("render_threads = 2", "render_threads = 1")
    if new == text:
        # Might already be 720p. Ensure threads = 1.
        import re
        new = re.sub(r"^render_threads\s*=\s*\d+", "render_threads = 1", text, flags=re.MULTILINE)
    TOML.write_text(new, encoding="utf-8")
    print(f"  [toml] output_preset=720p, render_threads=1")


def patch_builder_libx264() -> None:
    """Replace the libx264 flag tuple in builder.py with the most frugal
    possible: ultrafast preset, low crf, zerolatency tune."""
    text = BUILDER.read_text(encoding="utf-8")
    # The libx264 HardwareChoice block has a flag tuple that we want to
    # swap. We do this by string replacement of the two known shapes.
    new_flags = '("-preset", "ultrafast", "-crf", "22", "-tune", "zerolatency")'
    occurrences = 0
    # Shape 1: current (after our previous edit) — line with ("-preset", "veryfast", ...)
    for needle in [
        '("-preset", "veryfast", "-crf", "20", "-tune", "zerolatency")',
        '("-preset", "medium", "-crf", "20")',
    ]:
        if needle in text:
            text = text.replace(needle, new_flags)
            occurrences += text.count(new_flags) - (1 if needle != new_flags else 0)
    BUILDER.write_text(text, encoding="utf-8")
    print(f"  [builder] libx264 -> ultrafast + zerolatency")


def free_ram_check() -> float:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "[math]::Round((Get-CimInstance Win32_OperatingSystem).FreePhysicalMemory/1MB, 2)"],
        capture_output=True, text=True,
    )
    try:
        return float(out.stdout.strip())
    except ValueError:
        return -1.0


def clean_state() -> None:
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process ffmpeg -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue; "
         "Get-Process python -ErrorAction SilentlyContinue | "
         "Where-Object { $_.MainWindowTitle -like '*Sleep Learning Engine*' } | "
         "Stop-Process -Force -ErrorAction SilentlyContinue"],
        capture_output=True,
    )
    time.sleep(2)
    for path in (RENDER_OUT, RENDER_ERR):
        if path.exists():
            path.unlink()
    for mp4 in OUTPUT.glob("sleep_learning_engine-*.mp4"):
        if mp4.stat().st_size < 50_000_000:
            print(f"  [clean] removing partial {mp4.name} ({mp4.stat().st_size} bytes)")
            mp4.unlink()


def launch_render(stem: str) -> int:
    env = os.environ.copy()
    env["TMP"] = str(ROOT / "cache/tmp")
    env["TEMP"] = env["TMP"]
    (ROOT / "cache/tmp").mkdir(parents=True, exist_ok=True)
    cmd = [
        str(VENV_PY), "-m", "sleep_learning_engine", "render",
        "--script", SCRIPT,
        "--output-stem", stem,
        "--json",
    ]
    print(f"  [launch] {' '.join(cmd)}")
    proc = subprocess.Popen(
        cmd,
        cwd=str(ROOT),
        stdout=open(RENDER_OUT, "wb"),
        stderr=open(RENDER_ERR, "wb"),
        env=env,
    )
    return proc.pid


def is_alive(pid: int) -> bool:
    out = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         f"(Get-Process -Id {pid} -ErrorAction SilentlyContinue) -ne $null"],
        capture_output=True, text=True, timeout=5,
    )
    return "True" in out.stdout


def find_output(stem: str) -> Path | None:
    p = OUTPUT / f"{stem}.mp4"
    if p.exists() and p.stat().st_size > 100_000:
        return p
    return None


def kill_all() -> None:
    subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-Process ffmpeg -ErrorAction SilentlyContinue | Stop-Process -Force; "
         "Get-Process python -ErrorAction SilentlyContinue | "
         "Where-Object { $_.Path -like '*sleep_learning_engine*' } | Stop-Process -Force"],
        capture_output=True,
    )
    time.sleep(2)


def main() -> int:
    print(f"Free RAM at start: {free_ram_check():.2f} GB")

    # Apply the cheapest config
    patch_toml_preset_720p()
    patch_builder_libx264()

    clean_state()

    stem = f"sleep_learning_engine-720p-{time.strftime('%H%M%S')}"
    pid = launch_render(stem)
    print(f"  [pid] {pid}")

    start = time.time()
    last_report = 0.0
    oom_detected = False
    while time.time() - start < 1800:  # 30 min cap
        if not is_alive(pid):
            print(f"  [exit] process ended after {time.time()-start:.1f}s")
            break
        # Periodic status
        if time.time() - last_report > 30:
            out = find_output(stem)
            ram = free_ram_check()
            print(f"  [poll t+{time.time()-start:.0f}s] ram={ram:.2f}GB "
                  f"mp4={out.stat().st_size/1e6:.2f}MB" if out else
                  f"  [poll t+{time.time()-start:.0f}s] ram={ram:.2f}GB mp4=<none>")
            last_report = time.time()
        # Watch log for OOM marker
        if LOG.exists():
            tail = LOG.read_text(encoding="utf-8", errors="ignore")[-3000:]
            if "Cannot allocate memory" in tail or "Error sending frames" in tail:
                print("  [detect] OOM in log")
                oom_detected = True
                break
        time.sleep(5)
    else:
        print("  [timeout] 30 min cap reached")
        oom_detected = True

    if oom_detected:
        kill_all()
        print("FAILED: OOM")
        return 1

    out = find_output(stem)
    if out:
        print(f"\nSUCCESS: {out} ({out.stat().st_size/1e6:.2f} MB)")
        return 0

    # Process exited but no output
    kill_all()
    if RENDER_OUT.exists():
        print("Render stdout (last 2KB):")
        print(RENDER_OUT.read_text(encoding="utf-8", errors="ignore")[-2000:])
    if RENDER_ERR.exists():
        print("Render stderr (last 2KB):")
        print(RENDER_ERR.read_text(encoding="utf-8", errors="ignore")[-2000:])
    return 1


if __name__ == "__main__":
    sys.exit(main())
