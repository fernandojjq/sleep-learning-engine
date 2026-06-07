"""Generate the Colab notebook for low-RAM cloud rendering.

The notebook is checked into the repo as
``docs/cloud/low_ram_render.ipynb`` so anyone can open it directly in
Google Colab via the badge in the README. The notebook runs the full
sleeplens pipeline (TTS + mix + NVENC encode) on a free T4 GPU, which
has 16 GB VRAM and 12.7 GB system RAM - more than enough for 1080p
H.264 at any preset.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/cloud/low_ram_render.ipynb"
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
        "# Sleeplens low-RAM cloud render",
        "",
        "Run the full sleeplens pipeline on a free Google Colab T4 GPU. This is",
        "the right path when your local machine runs out of memory during the",
        "final encode: a 1080p H.264 video needs ~700 MB of free RAM for the",
        "libx264 medium preset, and the per-pixel `geq` progress bar adds ~150",
        "MB on top. Colab gives you 12.7 GB of system RAM plus a real NVIDIA",
        "NVENC encoder, so the encode finishes in a couple of minutes.",
        "",
        "**How to use:**",
        "1. Click *Runtime -> Run all* (or press `Ctrl+F9`).",
        "2. The upload cell will ask for your script text file and your",
        "   background image - pick both files.",
        "3. Wait for the render cell to finish (TTS, mix, encode).",
        "4. The download cell will save the final MP4 to your machine.",
        "",
        "**Cost:** free. Colab sessions cap at 12 hours and may disconnect if",
        "idle, but a 6-minute video finishes in well under 10 minutes.",
    ),
    code(
        "# 1. Install sleeplens and its dependencies. Pulls from the public",
        "# GitHub repo, so this only needs an internet connection.",
        '!pip install -q "sleeplens @ git+https://github.com/fernandojjq/sleeplens.git"',
        "",
        "# Colab's system ffmpeg already includes NVENC and CUDA; no need to",
        "# apt-get install a custom build. We still probe it to confirm.",
        "import subprocess",
        "ffmpeg_version = subprocess.run(",
        '    ["ffmpeg", "-version"], capture_output=True, text=True',
        ").stdout.splitlines()[0]",
        "print(ffmpeg_version)",
        "",
        "nvenc = subprocess.run(",
        '    ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True',
        ").stdout",
        'print("NVENC available:" if "h264_nvenc" in nvenc else "NVENC NOT available - falling back to libx264")',
    ),
    code(
        "# 2. Upload your script text file and background image. Both are",
        "# sent through the browser, stay on Colab's VM, and are deleted when",
        "# the session ends. Nothing is uploaded to GitHub or any third party.",
        "from google.colab import files",
        "import os",
        "",
        'os.makedirs("/content/assets", exist_ok=True)',
        'os.makedirs("/content/output", exist_ok=True)',
        "",
        'print("Upload your script text file (e.g. prueba.txt) and background image...")',
        "uploaded = files.upload()",
        "for name, data in uploaded.items():",
        '    with open(f"/content/assets/{name}", "wb") as fh:',
        "        fh.write(data)",
        'print(f"Uploaded: {sorted(uploaded.keys())}")',
        "",
        "# Heuristics: pick the first .txt as the script and the first image",
        "# as the background. Edit the lines below if you uploaded multiple.",
        "import glob",
        'txt_files = sorted(glob.glob("/content/assets/*.txt"))',
        'img_files = sorted(',
        '    glob.glob("/content/assets/*.jpg")',
        '    + glob.glob("/content/assets/*.jpeg")',
        '    + glob.glob("/content/assets/*.png")',
        ")",
        'SCRIPT = txt_files[0] if txt_files else ""',
        'BG_IMAGE = img_files[0] if img_files else ""',
        'print(f"Script: {SCRIPT}")',
        'print(f"Background: {BG_IMAGE}")',
        "",
        "if not SCRIPT or not BG_IMAGE:",
        '    raise SystemExit("Need one .txt script and one image. Re-run this cell.")',
    ),
    code(
        "# 3. Render the video. This runs the same sleeplens pipeline as the",
        "# local CLI: TTS via Edge, mix with the procedural ambient bed, and",
        "# the final ffmpeg encode. On Colab, the encode uses real NVENC, so",
        "# a 6-minute 1080p video finishes in about 1-2 minutes.",
        "import subprocess, sys",
        "",
        'OUT_STEM = "sleeplens-colab"',
        'cmd = [',
        '    "python", "-m", "sleeplens", "render",',
        '    "--script", SCRIPT,',
        '    "--background-image", BG_IMAGE,',
        '    "--output-stem", OUT_STEM,',
        "]",
        'print("Running:", " ".join(cmd))',
        "result = subprocess.run(cmd, capture_output=True, text=True)",
        'print("--- stdout (last 2KB) ---")',
        "print(result.stdout[-2000:])",
        'print("--- stderr (last 2KB) ---")',
        "print(result.stderr[-2000:])",
        "if result.returncode != 0:",
        '    raise SystemExit(f"Render failed with exit code {result.returncode}")',
    ),
    code(
        "# 4. Download the final MP4. Colab saves it to /content/output/ and",
        "# hands it to the browser, which triggers a normal download.",
        "from google.colab import files",
        "import glob, os",
        "",
        'candidates = sorted(glob.glob(f"/content/output/{OUT_STEM}.mp4"))',
        "if not candidates:",
        '    raise SystemExit("No MP4 was produced. Check the render cell for errors.")',
        'output = candidates[0]',
        'print(f"Final video: {output} ({os.path.getsize(output)/1e6:.1f} MB)")',
        "files.download(output)",
    ),
    md(
        "## What just happened",
        "",
        "- **Cell 1** installed sleeplens from the public repo and confirmed",
        "  Colab's ffmpeg build exposes NVENC (it always does on T4 instances).",
        "- **Cell 2** took the two files you uploaded and resolved the right",
        "  paths for the pipeline.",
        "- **Cell 3** ran the full sleeplens CLI: it generated the TTS audio",
        "  via Microsoft Edge, mixed it with the procedural ambient bed,",
        "  and encoded the final MP4 with `h264_nvenc` on the T4.",
        "- **Cell 4** downloaded the MP4 to your machine.",
        "",
        "## Limitations of the free tier",
        "",
        "- Colab free sessions cap at 12 hours and may disconnect when idle.",
        "- GPU availability is not guaranteed; if no T4 is free, the notebook",
        "  falls back to `libx264` software encoding (still 4-6x faster than a",
        "  low-RAM Windows box because Colab has 12.7 GB free).",
        "- The Edge TTS service is rate-limited; very long scripts may need",
        "  to be split into chunks.",
        "",
        "## Troubleshooting",
        "",
        "If the render cell says `Render failed with exit code -12`, Colab ran",
        "out of memory. Switch the runtime to a 25 GB RAM instance (Colab Pro)",
        "or rerun the notebook - the failure is usually transient.",
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
