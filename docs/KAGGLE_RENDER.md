# Cloud rendering on Kaggle

Kaggle is the right platform when the local box runs out of memory
during the 1080p encode, AND you have a recurring workflow that
benefits from a persistent dataset (50+ ambient tracks, a backlog
of scripts, etc.). The Colab notebook at
[low_ram_render.ipynb](low_ram_render.ipynb) covers the one-off
case; this one is for the power user.

## Why ship both Colab and Kaggle notebooks

They have different cost/benefit profiles and solve different
problems:

| | Colab free | Kaggle free |
|---|---|---|
| GPU access | Best-effort, may assign 0/15 GB | Guaranteed 2x T4 (30 GB VRAM) |
| Weekly quota | None - session can drop any time | 30 GPU hours/week |
| Session length | 12 h, can be killed when idle | 12 h per notebook run, persists |
| Datasets | No equivalent - re-upload every time | Yes, upload once, reuse forever |
| Working storage | 78 GB, wiped on session end | 20 GB, persists across sessions |
| Setup time | 30 s | 2 min (upload dataset once) |
| Internet | Always on | Toggle in settings |

**Use Colab when:** you want a quick one-off render, no large
ambient library, no patience for Kaggle's account verification
flow. The current free Colab tier can be enough if you only render
a couple of videos a month.

**Use Kaggle when:** you have 50+ ambient tracks you do not want to
re-upload, you run renders on a schedule, or you need a T4
guaranteed (Colab is best-effort and the 0/15 GB "no GPU available"
message is common during peak hours). 30 GPU hours per week is
enough for ~20-30 six-minute videos.

## How to use the Kaggle notebook

1. **Upload your ambient library as a Kaggle dataset.** This is a
   one-time cost: go to `kaggle.com/datasets/new`, drag your 96
   `.mp3` files in, title the dataset `ambient` (or any kebab-case
   slug). The notebook reads from `/kaggle/input/<slug>/`.
2. **(Optional) Upload your script and background image as a second
   dataset** named `sleep_learning_engine-assets`, so the notebook picks them
   up automatically. If you skip this, the notebook can generate
   the script in-cell from a topic.
3. **Open the notebook** at `kaggle.com/code` -> New Notebook.
   Settings: **Accelerator = GPU T4 x2**, **Internet = On**.
4. **Add your `ambient` dataset** via the right-side panel ->
   `+ Add data` -> search for your dataset -> Add.
5. **Run all cells.** A 6-minute 1080p video finishes in 1-2
   minutes of GPU time, plus ~40 s of Edge TTS overhead.

## What the notebook does

| Cell | Purpose | Time |
|------|---------|------|
| 1    | Intro (markdown) | - |
| 2    | Install sleep_learning_engine from GitHub, confirm NVENC | ~30 s |
| 3    | Set up paths, copy ambient from dataset to working dir | ~10 s |
| 4    | Optional: generate the script from a topic in-notebook | user-driven |
| 5    | Run the sleep_learning_engine render with T4 NVENC encode | ~1-2 min |
| 6    | Locate the output MP4, print instructions to download | - |
| 7    | Colab vs Kaggle notes (markdown) | - |

## Limitations of the free tier

- **20 GB working storage cap.** Long scripts (2+ hours) fill this
  with cached TTS segments. Run `!rm -rf /kaggle/working/cache/*`
  between renders if you hit it.
- **30 GPU hours per week, per account.** Resets on Monday. Each
  6-minute 1080p render costs ~2 min of GPU, so the budget allows
  for ~900 renders per week in theory. Realistically you will hit
  the 12-hour-per-notebook limit before the weekly cap.
- **Internet must be explicitly enabled** in settings. Without
  it, the `pip install` and Edge TTS calls fail.
- **Background videos over 4K** are filtered by Kaggle. Stick to
  1080p for the background source and let the encoder upscale.

## If you want to script batch renders

Kaggle has a CLI and an API. The notebook can be invoked from a
script with the Kaggle API (`kaggle kernels push -k <username>/<slug>`),
and the output files are addressable from another notebook. This
makes "render every script in a folder overnight" a real workflow
rather than a manual loop. We have not built a wrapper for this
yet - the use case is real but narrow (one-off for now).
