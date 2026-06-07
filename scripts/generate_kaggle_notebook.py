"""Generate the Kaggle notebook for low-RAM cloud rendering with persistent
datasets.

The notebook is checked into the repo as
``docs/cloud/kaggle_render.ipynb`` so users can open it directly in
Kaggle via the badge in the README. The notebook runs the full
sleeplens pipeline on a free T4 GPU (2x T4 = 30 GB VRAM, 30 h/week
quota) and reads ambient tracks from a user-uploaded dataset so the
96-mp3 library does not have to be re-uploaded per session.

Kaggle vs Colab (the reasons for shipping both):
* Colab: 12 h/session, GPU is best-effort and may be 0/15 GB.
  Good for a one-off render.
* Kaggle: 30 h/week of guaranteed T4, persistent datasets, working
  directory survives between sessions. Better for a recurring
  workflow where the user has 50+ ambient tracks and a backlog of
  scripts to render.

The notebook generation is a copy of the Colab one adapted to
``/kaggle/input/`` (read-only datasets) and ``/kaggle/working/``
(writable, persistent). The structure is identical to the Colab
notebook so the same cell numbers work in both environments.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs/cloud/kaggle_render.ipynb"
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
        "# Sleeplens on Kaggle (persistent ambient + reliable T4 GPU)",
        "",
        "This notebook is the Kaggle counterpart of the Colab one.",
        "Use it when:",
        "",
        "- You have a **large ambient library** (50+ tracks) you do not",
        "  want to re-upload every session. Upload it once as a Kaggle",
        "  dataset and read from ``/kaggle/input/<dataset-slug>/``.",
        "- You need a **guaranteed T4 GPU** (Colab is best-effort and may",
        "  assign 0/15 GB). Kaggle gives 2x T4 (30 GB VRAM) and 30 h/week",
        "  of GPU time per account.",
        "- You want the **working directory to persist** between sessions",
        "  so the cached TTS segments and procedural ambients do not",
        "  regenerate every time.",
        "",
        "**One-time setup** (in your Kaggle account, not in the notebook):",
        "",
        "1. Go to `kaggle.com/datasets/new` and upload your 96 ambient",
        "   tracks. Title the dataset `ambient` (or any kebab-case slug).",
        "2. (Optional) Upload your script.txt and background image as a",
        "   second dataset called `sleeplens-assets`, so the notebook can",
        "   pick them up without manual upload.",
        "3. Open this notebook in Kaggle, set **Accelerator = GPU T4 x2**",
        "   and **Internet = On** in the Settings panel.",
        "4. Click **+ Add data** in the right panel and add your `ambient`",
        "   dataset (and `sleeplens-assets` if you made one).",
        "5. Run all cells.",
        "",
        "**Cost:** free. 30 GPU hours per week, 20 GB of working storage",
        "that persists across sessions.",
    ),
    code(
        "# 1. Install sleeplens from the public repo. Pulls the latest",
        "# main branch; pin a tag if you want a specific version.",
        "!pip install -q \"sleeplens @ git+https://github.com/fernandojjq/sleeplens.git\"",
        "",
        "# Confirm ffmpeg is present and NVENC is exposed. Kaggle's",
        "# base image ships a recent ffmpeg with the NVIDIA codec",
        "# headers compiled in, so the canary should pass on T4.",
        "import subprocess",
        "ffmpeg_version = subprocess.run(",
        '    ["ffmpeg", "-version"], capture_output=True, text=True',
        ").stdout.splitlines()[0]",
        "print(ffmpeg_version)",
        "",
        "nvenc = subprocess.run(",
        '    ["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True',
        ").stdout",
        'print("NVENC available:" if "h264_nvenc" in nvenc else "NVENC NOT available - libx264 fallback")',
    ),
    code(
        "# 2. Set up the paths. Kaggle's filesystem is split:",
        "#   /kaggle/input/  - read-only, where your datasets live",
        "#   /kaggle/working/ - writable, persists between sessions",
        "# Sleeplens writes mixed audio, encoded video, and cached TTS",
        "# segments, so we point all of that at /kaggle/working/.",
        "import os, shutil, glob",
        "",
        'WORK = "/kaggle/working"',
        'ASSETS = f"{WORK}/assets"',
        'CACHE = f"{WORK}/cache"',
        'OUTPUT = f"{WORK}/output"',
        "",
        "for d in (ASSETS, CACHE, OUTPUT, f\"{ASSETS}/ambient\"):",
        "    os.makedirs(d, exist_ok=True)",
        "",
        "# Copy the ambient library from the read-only dataset into the",
        "# working directory so the sleeplens scanner can read it. This",
        "# is a one-time copy per session; subsequent cells skip files",
        "# that already exist.",
        'AMBIENT_SRC_SLUG = "ambient"  # change to your dataset slug if different',
        f'AMBIENT_SRC = f"/kaggle/input/{{AMBIENT_SRC_SLUG}}"',
        f'AMBIENT_DST = f"{{ASSETS}}/ambient"',
        "",
        "if os.path.exists(AMBIENT_SRC):",
        "    copied = 0",
        "    for ext in (\"mp3\", \"ogg\", \"wav\", \"flac\", \"m4a\", \"aac\"):",
        '        for src in glob.glob(f"{AMBIENT_SRC}/*.{ext}"):',
        '            dst = os.path.join(AMBIENT_DST, os.path.basename(src))',
        "            if not os.path.exists(dst):",
        "                shutil.copy2(src, dst)",
        "                copied += 1",
        "    total = len(glob.glob(f\"{AMBIENT_DST}/*\"))",
        '    print(f"Ambient library: {total} tracks ({copied} new this session)")',
        "else:",
        '    print(f"WARNING: {AMBIENT_SRC} not found.")',
        '    print("Add your ambient dataset via the + Add data panel.")',
    ),
    code(
        "# 3. (Optional) Render the script with a topic. Set",
        "# USE_TOPIC = True to skip the script.txt upload and have Kaggle",
        "# call your AI provider directly. Leave it False to use the",
        "# script.txt that lives in your `sleeplens-assets` dataset.",
        "import os, subprocess",
        "",
        "USE_TOPIC = False  # flip to True to enable in-notebook script generation",
        'TOPIC = ""  # e.g. "the discovery of penicillin"',
        "TARGET_WORDS = 4500",
        'API_KEY = ""  # your NVIDIA NIM key (or OpenAI key, or ...)',
        'BASE_URL = "https://integrate.api.nvidia.com/v1"',
        'MODEL = "deepseek-ai/deepseek-v4-flash"',
        "",
        "if USE_TOPIC:",
        "    if not TOPIC or not API_KEY:",
        '        raise SystemExit("Set TOPIC and API_KEY first.")',
        "    from openai import OpenAI",
        "    from sleeplens.ai.script_writer import SYSTEM_PROMPT",
        "    client = OpenAI(base_url=BASE_URL, api_key=API_KEY, timeout=180.0)",
        '    user_prompt = f"Topic: {TOPIC}\\nTarget word count: {TARGET_WORDS}."',
        "    response = client.chat.completions.create(",
        "        model=MODEL,",
        "        messages=[",
        '            {"role": "system", "content": SYSTEM_PROMPT},',
        '            {"role": "user", "content": user_prompt},',
        "        ],",
        "        temperature=0.7, max_tokens=8192,",
        "    )",
        "    generated = response.choices[0].message.content",
        '    safe_topic = TOPIC.replace(" ", "_")[:40]',
        f'    SCRIPT = f"{{ASSETS}}/{{safe_topic}}.txt"',
        '    with open(SCRIPT, "w", encoding="utf-8") as fh:',
        "        fh.write(generated)",
        '    print(f"Generated {len(generated.split())} words -> {SCRIPT}")',
        "else:",
        '    # Use the script from the sleeplens-assets dataset. Adjust the',
        '    # slug to match your dataset name.',
        '    SCRIPT = "/kaggle/input/sleeplens-assets/prueba.txt"',
        '    BG_IMAGE = "/kaggle/input/sleeplens-assets/background.jpg"',
        '    BG_VIDEO = "/kaggle/input/sleeplens-assets/background.mp4"',
        '    print(f"Script: {SCRIPT}")',
        '    print(f"Background image: {BG_IMAGE}")',
    ),
    code(
        "# 4. Render. The ffmpeg encode uses real NVENC on the T4, so a",
        "# 6-minute 1080p video finishes in about 1-2 minutes.",
        "import os, subprocess, sys",
        "",
        f'OUT_STEM = "sleeplens-kaggle"',
        'cmd = [',
        '    "python", "-m", "sleeplens", "render",',
        '    "--script", SCRIPT,',
        '    "--output-stem", OUT_STEM,',
        "]",
        "if os.path.exists(BG_IMAGE):",
        '    cmd += ["--background-image", BG_IMAGE]',
        "elif os.path.exists(BG_VIDEO):",
        '    cmd += ["--background-video", BG_VIDEO]',
        "",
        f'env = {{**os.environ, "TMP": "{{CACHE}}", "TEMP": "{{CACHE}}"}}',
        "print(\"Running:\", \" \".join(cmd))",
        "result = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=WORK)",
        'print("--- stdout (last 2KB) ---")',
        "print(result.stdout[-2000:])",
        'print("--- stderr (last 2KB) ---")',
        "print(result.stderr[-2000:])",
        "if result.returncode != 0:",
        '    raise SystemExit(f"Render failed with exit code {result.returncode}")',
    ),
    code(
        "# 5. Locate the final MP4 and print its path. The file lives in",
        "# /kaggle/working/output/ and survives this session, so you can",
        "# come back tomorrow, open the same notebook, and the file is",
        "# still there to download.",
        "import glob, os",
        "",
        "candidates = sorted(glob.glob(f'/kaggle/working/output/{OUT_STEM}.mp4'))",
        "if not candidates:",
        '    raise SystemExit("No MP4 was produced. Check the render cell for errors.")',
        "output = candidates[0]",
        'print(f"Final video: {output}")',
        'print(f"Size: {os.path.getsize(output)/1e6:.1f} MB")',
        'print("")',
        'print("To download:")',
        'print("  - In the Kaggle UI, expand the right panel Output")',
        'print("  - Click the file -> Download")',
        'print("  - Or copy it to a dataset with:")',
        'print(f"    !cp {output} /kaggle/input/<your-dataset>/")',
    ),
    md(
        "## When to use this notebook vs the Colab one",
        "",
        "- **Use Kaggle** (this notebook) when you have a large ambient",
        "  library, want a guaranteed T4, and run renders regularly.",
        "  30 GPU hours per week is more than enough for a backlog of",
        "  scripts.",
        "- **Use Colab** (`docs/cloud/low_ram_render.ipynb`) for a quick",
        "  one-off render with no setup. Internet, GPU, and files are",
        "  ready in 30 seconds. The trade-off is that the GPU is",
        "  best-effort and may not be available at peak times.",
        "- **Use the local GUI** (`uv run python run.py`) when you have",
        "  8+ GB of free RAM and want full offline control.",
        "",
        "## Troubleshooting",
        "",
        "- **`/kaggle/input/ambient` not found.** You forgot to add the",
        "  dataset via the + Add data panel. Add it, then re-run cell 2.",
        "- **Render is slow (10+ min).** Your runtime is on CPU. Check",
        "  Settings -> Accelerator and pick GPU T4 x2. Kaggle usually",
        "  grants the T4 within seconds; if it does not, save the version",
        "  and try again in a few minutes.",
        "- **Edge TTS rate-limited.** Microsoft throttles to about 1",
        "  request per second on the free service. For a 35-segment",
        "  script, plan for ~40 s of TTS time on top of the encode.",
        "- **Out of /kaggle/working space.** 20 GB cap. If your script",
        "  is very long, the cached TTS segments can fill it. Run",
        "  `!rm -rf /kaggle/working/cache/*` between renders.",
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
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {OUT} ({OUT.stat().st_size/1024:.1f} KB)")
