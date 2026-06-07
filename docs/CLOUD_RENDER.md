# Cloud rendering on Google Colab

If your local machine runs out of memory during the final 1080p
encode, sleep_learning_engine can run the full pipeline on a free Google Colab
T4 GPU. The Colab VM has 12.7 GB of system RAM plus a real NVIDIA
NVENC encoder, which is enough headroom for any 1080p encode
configuration.

> **Prefer Kaggle?** If you have a large ambient library or render
> regularly, the [Kaggle notebook](KAGGLE_RENDER.md) gives you a
> guaranteed 2x T4 GPU, 30 GPU hours per week, and persistent
> datasets. Use Colab for one-off renders, Kaggle for everything
> else.

## When to use this

Use the cloud path when you see one of these errors in the local
log:

- `Error sending frames to consumers: Cannot allocate memory`
- `ffmpeg exited with code 4294967284` (this is `-12` = ENOMEM,
  decimal `-12`, two's complement unsigned)
- The render hangs at frame 100-300 and the output MP4 stays
  under 2 MB

A 1080p H.264 encode typically needs 500-800 MB of free RAM on
top of what the OS and background apps are using. If your
`TotalVisibleMemorySize - FreePhysicalMemory` is above 6 GB on
a 8 GB Windows box, the encode will OOM.

## How to use it

### Option A: open the notebook directly

Click the badge in the README, or open this URL in your browser:

```
https://colab.research.google.com/github/fernandojjq/sleep_learning_engine/blob/main/docs/cloud/low_ram_render.ipynb
```

Then click **Runtime -> Run all** (or press `Ctrl+F9`).

### Option B: launch from the CLI

From the sleep_learning_engine project directory:

```bash
uv run python -m sleep_learning_engine cloud
```

The command validates your local state (script file and background
image are reachable), prints the Colab URL, and opens it in your
default browser. The same steps as Option A follow.

Use `--no-browser` to print the URL without launching the browser,
or `--repo` / `--branch` if you are working from a fork.

## What the notebook does

| Cell | Purpose | Time |
|------|---------|------|
| 1    | Intro and instructions (markdown) | - |
| 2    | Install sleep_learning_engine from the public repo, confirm NVENC is available | ~30 s |
| 3    | Upload the script text file and the background image (browser-driven) | user-driven |
| 4    | Run the sleep_learning_engine render CLI: TTS via Edge, mix with ambient bed, encode with NVENC | ~5 min |
| 5    | Download the final MP4 to your machine | user-driven |
| 6    | Troubleshooting notes (markdown) | - |

The end-to-end wall time for a 6-minute 1080p video is about
5-10 minutes, dominated by the Edge TTS calls (1-2 s per segment).

## Limitations of the free tier

- **Session length:** 12 hours max, may disconnect when idle.
- **GPU availability:** T4 access is best-effort. If no T4 is free,
  the notebook falls back to `libx264` (no NVENC) on the CPU. This
  is still 4-6x faster than a low-RAM Windows box because Colab has
  12.7 GB free.
- **Storage:** the Colab VM is wiped when the session ends. Anything
  you want to keep must be downloaded before you close the tab.
- **Edge TTS rate limits:** Microsoft Edge is rate-limited; very
  long scripts (over 2 hours of audio) may need to be split into
  chunks.
- **Uploads:** the script text and background image go through the
  Colab upload widget, which runs in your browser and is not stored
  on any server. Colab's terms of service apply.

## If the render fails on Colab

The most common failure is the same ENOOM as locally, usually
because the runtime was assigned a smaller machine. Rerun the
notebook - the failure is usually transient. If it persists, switch
to Colab Pro for a 25 GB RAM instance.

## Cost

The free tier is genuinely free. Google does not ask for a credit
card to use Colab; you only need a Google account (the same one
you use for Gmail, Drive, etc.). Colab Pro is $9.99/month and gives
you faster GPUs, longer sessions, and more RAM, but is not required
for sleep_learning_engine renders.

## Alternative: Kaggle

For a recurring workflow with a persistent ambient dataset, see
[KAGGLE_RENDER.md](KAGGLE_RENDER.md). The trade-off matrix:

| | Colab | Kaggle |
|---|---|---|
| GPU | Best-effort T4 | Guaranteed 2x T4 |
| Weekly quota | None (session-based) | 30 GPU hours/week |
| Persistent datasets | No | Yes |
| Setup time | 30 s | 2 min one-time |
| Best for | One-off renders | Recurring renders with large libraries |
