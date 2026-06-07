"""Generate a Drive-backed Colab notebook for a recurring rendering
workflow with a persistent ambient library.

This is the "personal" notebook counterpart to the public one
at ``docs/cloud/low_ram_render.ipynb``. Differences from the
public one:

1. The ambient library lives in Google Drive and is mounted
   on every session instead of being re-uploaded.
2. The script and background image can also live in Drive so a
   recurring workflow only needs the new file uploaded (or even
   pre-staged in Drive if the user prefers).
3. The GPU / NVENC check in cell 1 is more honest: it runs
   ``nvidia-smi`` to actually verify the runtime has a GPU,
   instead of trusting the ffmpeg encoder list (which lies
   about NVENC being available when the CUDA runtime is
   missing).

Recommended Drive layout:

    My Drive/
    └── sleep-learning-engine/
        ├── ambient/      # 96+ normalised mp3 / ogg tracks
        ├── scripts/      # one or more .txt scripts
        └── images/       # background images / short loop videos

The notebook is generated from a Python source-of-truth so cell
content stays in sync with the rest of the codebase.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/cloud/drive_render.ipynb"
OUT.parent.mkdir(parents=True, exist_ok=True)


def md(*lines: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": [ln if ln.endswith("\n") else ln + "\n" for ln in lines][:-1]
        + [lines[-1]],
    }


def code(*lines: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": [ln if ln.endswith("\n") else ln + "\n" for ln in lines][:-1]
        + [lines[-1]],
    }


cells = [
    md(
        "# Sleep Learning Engine - Drive-backed low-RAM cloud render",
        "",
        "This notebook is the **personal / recurring-render** variant of",
        "the public Colab notebook at `docs/cloud/low_ram_render.ipynb`.",
        "Use it when you have a stable ambient library and a recurring",
        "render workflow:",
        "",
        "- The 97 normalised ambient mp3 files live in Drive and are",
        "  mounted on every Colab session (cell 2). You upload them",
        "  **once** and forget about them.",
        "- The script and the background image or video change with",
        "  every project, so you upload them fresh at the start of",
        "  each render (cell 3).",
        "",
        "**Recommended Drive layout** (create it once, reuse forever):",
        "",
        "```",
        "My Drive/",
        "└── sleep-learning-engine/",
        "    └── ambient/      <- 97 normalised mp3 tracks (persistent)",
        "```",
        "",
        "The script and background image are uploaded per-session and",
        "are NOT stored in Drive (they change with every project).",
        "",
        "**Runtime setup (one-time, every fresh Colab session):**",
        "1. Runtime -> Change runtime type -> T4 GPU -> RAM amplia = On -> Save",
        "2. Reconnect when prompted",
        "3. Click Runtime -> Run all (Ctrl+F9)",
        "",
        "**Cost:** free. Colab free sessions cap at 12 hours. A 6-minute",
        "video finishes in well under 10 minutes end-to-end.",
    ),
    code(
        "# 1. Install sleep_learning_engine from the public repo. Tarball URL",
        "# (not a git clone) so pip does not need git credentials.",
        "!pip install -q https://github.com/fernandojjq/sleep-learning-engine/archive/refs/heads/main.tar.gz",
        "",
        "# Verify the runtime actually has a GPU. The previous version only",
        "# checked the ffmpeg encoder list, which lies: h264_nvenc can be in",
        "# the list even when no GPU is bound to the container. The real test",
        "# is nvidia-smi (raises if no GPU is present).",
        "import subprocess",
        "smi = subprocess.run(",
        '    ["nvidia-smi", "--query-gpu=name,memory.total,driver_version",',
        '     "--format=csv,noheader"], capture_output=True, text=True, timeout=15',
        ")",
        "if smi.returncode == 0 and smi.stdout.strip():",
        '    print("GPU detected:")',
        "    print(smi.stdout)",
        "else:",
        '    print("=" * 60)',
        '    print("NO GPU DETECTED in this Colab runtime.")',
        '    print("Encode will fall back to libx264 (CPU), 5-10x slower.")',
        '    print("")',
        '    print("Fix: Runtime -> Change runtime type -> T4 GPU -> Save.")',
        '    print("Reconnect when prompted. Re-run this cell.")',
        '    print("=" * 60)',
        "",
        "nvenc = subprocess.run(",
        '    ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True',
        ").stdout",
        'if "h264_nvenc" in nvenc:',
        '    print("NVENC encoder: AVAILABLE")',
        "else:",
        '    print("NVENC encoder: NOT in ffmpeg build (libx264 fallback)")',
    ),
    code(
        "# 2. Mount Google Drive and copy the persistent ambient library",
        "# into the writable working directory. This is a one-time copy per",
        "# session; subsequent cells skip files that already exist.",
        "from google.colab import drive",
        "import os, shutil, glob",
        "",
        "# Path conventions (edit if you put things elsewhere):",
        "DRIVE_ROOT = \"/content/drive/MyDrive/sleep-learning-engine\"",
        'AMBIENT_SRC = f"{DRIVE_ROOT}/ambient"',
        "WORK = \"/content/working\"",
        'ASSETS = f"{WORK}/assets"',
        'AMBIENT_DST = f"{ASSETS}/ambient"',
        "",
        "# Mount. force_remount=False avoids the OAuth popup when the",
        "# session was started with Drive already attached. The first",
        "# time in a session this WILL pop up a Google login.",
        "drive.mount('/content/drive', force_remount=False)",
        "",
        "for d in (ASSETS, AMBIENT_DST, f\"{WORK}/output\"):",
        "    os.makedirs(d, exist_ok=True)",
        "",
        "if not os.path.exists(AMBIENT_SRC):",
        '    print(f"WARNING: {AMBIENT_SRC} not found.")',
        '    print("Create the folder in Drive, upload the mp3 files, then re-run this cell.")',
        "else:",
        "    copied = 0",
        "    for ext in (\"mp3\", \"ogg\", \"wav\", \"flac\", \"m4a\", \"aac\"):",
        '        for src in glob.glob(f"{AMBIENT_SRC}/*.{ext}"):',
        '            dst = os.path.join(AMBIENT_DST, os.path.basename(src))',
        "            if not os.path.exists(dst):",
        "                shutil.copy2(src, dst)",
        "                copied += 1",
        "    total = len(glob.glob(f\"{AMBIENT_DST}/*\"))",
        '    print(f"Ambient library: {total} tracks ({copied} new this session)")',
    ),
    code(
        "# 3. Upload the script and the background image (or short video) for",
        "# THIS render. The script and background change with every project,",
        "# so the only thing that is persistent across renders is the ambient",
        "# library (handled in cell 2 via Drive).",
        "from google.colab import files",
        "import os, glob, shutil",
        "",
        "print(\"Upload the script text file (.txt) and the background image or video for THIS render...\")",
        "uploaded = files.upload()",
        "for name, data in uploaded.items():",
        "    target = f\"{ASSETS}/{name}\"",
        "    with open(target, \"wb\") as fh:",
        "        fh.write(data)",
        "print(f\"Uploaded: {sorted(uploaded.keys())}\")",
        "",
        "# Resolve the paths. First .txt is the script, first video is the",
        "# loopable background, first image is the still background.",
        "SCRIPT = \"\"",
        "for pat in (\"*.txt\",):",
        "    matches = sorted(glob.glob(f\"{ASSETS}/{pat}\"))",
        "    if matches:",
        "        SCRIPT = matches[0]",
        "        break",
        "",
        "BG_IMAGE = \"\"",
        "BG_VIDEO = \"\"",
        "for pat in (\"*.mp4\", \"*.mov\", \"*.webm\"):",
        "    matches = sorted(glob.glob(f\"{ASSETS}/{pat}\"))",
        "    if matches:",
        "        BG_VIDEO = matches[0]",
        "        break",
        "if not BG_VIDEO:",
        "    for pat in (\"*.jpg\", \"*.jpeg\", \"*.png\"):",
        "        matches = sorted(glob.glob(f\"{ASSETS}/{pat}\"))",
        "        if matches:",
        "            BG_IMAGE = matches[0]",
        "            break",
        "",
        "print(f\"Script:      {SCRIPT or '<missing>'}\")",
        "print(f\"Background:  {BG_IMAGE or BG_VIDEO or '<missing>'}\")",
        "print(f\"  is video:  {bool(BG_VIDEO)}\")",
        "",
        "if not SCRIPT:",
        "    raise SystemExit(\"Need a .txt script. Upload one in this cell.\")",
        "if not (BG_IMAGE or BG_VIDEO):",
        "    raise SystemExit(\"Need a background image or video. Upload one in this cell.\")",
        "",
        "# Optional: pull the script/image from Drive instead. Uncomment to use.",
        "# Useful when you have a recurring topic (same script, new ambient).",
        "# SCRIPT = f\"{DRIVE_ROOT}/scripts/prueba.txt\"",
        "# BG_IMAGE = f\"{DRIVE_ROOT}/images/logo_sleeping_dev.jpeg\"",
    ),
    code(
        "# 4. Render. The ffmpeg encode uses real NVENC on the T4. A 6-minute",
        "# 1080p video finishes in 1-2 minutes of GPU time. The sleep_learning_engine",
        "# CLI streams its progress to stdout - look for 'Building ambient playlist'",
        "# and 'Rendered TTS segment N' as it runs.",
        "import os, subprocess",
        "",
        'OUT_STEM = "sleep_learning_engine-drive"',
        'cmd = [',
        '    "python", "-m", "sleep_learning_engine", "render",',
        '    "--script", SCRIPT,',
        '    "--output-stem", OUT_STEM,',
        "]",
        "if os.path.exists(BG_IMAGE):",
        '    cmd += ["--background-image", BG_IMAGE]',
        "",
        'env = {**os.environ, "TMP": WORK, "TEMP": WORK}',
        'print("Running:", " ".join(cmd))',
        "result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=WORK)",
        'print("--- stdout (last 2KB) ---")',
        "print(result.stdout[-2000:])",
        'print("--- stderr (last 2KB) ---")',
        "print(result.stderr[-2000:])",
        "if result.returncode != 0:",
        '    raise SystemExit(f"Render failed with exit code {result.returncode}")',
    ),
    code(
        "# 5. Locate the final MP4 and download it to your machine.",
        "import glob, os",
        "from google.colab import files",
        "",
        f'candidates = sorted(glob.glob(f"{{WORK}}/output/{{OUT_STEM}}.mp4"))',
        "if not candidates:",
        '    raise SystemExit("No MP4 was produced. Check the render cell for errors.")',
        "output = candidates[0]",
        'print(f"Final video: {output}")',
        'print(f"Size: {os.path.getsize(output)/1e6:.1f} MB")',
        "files.download(output)",
    ),
    md(
        "## Why this notebook and not the public one",
        "",
        "The public `docs/cloud/low_ram_render.ipynb` asks you to re-upload",
        "all 96 ambient mp3 files at the start of every session. If you",
        "render more than once a week, that 5-10 min upload is friction",
        "this notebook removes by mounting Drive and pulling the library",
        "from there.",
        "",
        "Both notebooks run the same `sleep_learning_engine` pipeline and",
        "produce identical MP4s. Use whichever matches your workflow.",
        "",
        "## When to use Kaggle instead",
        "",
        "If you find yourself running this notebook many times per week,",
        "and you want guaranteed T4 GPU access (Colab free is best-effort,",
        "can be 0/15 GB during peak hours), the Kaggle notebook at",
        "`docs/cloud/kaggle_render.ipynb` is the right answer. Kaggle",
        "gives 2x T4 (30 GB VRAM) and 30 GPU hours/week. The dataset path",
        "is different: you upload the mp3 files as a Kaggle dataset at",
        "`/kaggle/input/<slug>/` instead of Google Drive.",
    ),
]

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {
            "display_name": "Python 3",
            "language": "python",
            "name": "python3",
        },
        "language_info": {
            "name": "python",
            "version": "3.10",
        },
        "colab": {
            "provenance": [],
            "gpuType": "T4",
        },
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {OUT} ({OUT.stat().st_size/1024:.1f} KB)")
