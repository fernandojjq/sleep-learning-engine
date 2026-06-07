# Hardware and encoder notes

This page covers the encoder-specific details behind the
`hardware_accel` dropdown in the GUI. Start at
[README.md > Hardware requirements](../README.md#hardware-requirements)
if you have not yet decided between local and cloud.

## Encoder cheat sheet

| Encoder | Needs | RAM (1080p medium) | Speed vs libx264 medium | When to pick it |
|---|---|---|---|---|
| `h264_nvenc` | NVIDIA GPU + CUDA runtime + driver 470+ | ~400 MB | 5-10x faster | You have a discrete NVIDIA card and the driver works |
| `h264_qsv` | Intel iGPU/dGPU + Intel graphics driver | ~400 MB | 3-5x faster | You have an 8th-gen+ Intel CPU with integrated graphics |
| `h264_amf` | AMD GPU + AMF runtime | ~400 MB | 3-5x faster | You have an AMD discrete card |
| `libx264 medium` | nothing | ~700 MB | 1x (baseline) | Default for "auto" when no HW encoder works |
| `libx264 ultrafast` | nothing | ~150 MB | 0.4x (slower, but smaller files than you'd think) | Low-RAM Windows boxes that OOM with medium |

## "auto" mode

`auto` runs a one-frame canary encode for each candidate (NVENC,
QSV, AMF) in order. The first one that initializes successfully
wins. ffmpeg's `h264_nvenc` entry in `-encoders` proves the encoder
is **compiled in**, not that it can **initialize** - the canary
catches the case where the CUDA runtime is missing or the driver
is too old. On a 8 GB Windows laptop with no discrete GPU, the
canary chain falls through to `libx264`.

If the chosen HW encoder also fails at full encode time (rare, but
some Intel QSV builds pass the 1-frame canary on software
emulation and then choke at scale), the build retries once with
`libx264` and surfaces a warning in the log.

## Verifying your setup

```bash
# List available encoders.
uv run cache/ffmpeg.exe -hide_banner -encoders | findstr h264

# Canary-style probe. Replace the encoder name with yours.
uv run cache/ffmpeg.exe -y -hide_banner -loglevel error \
  -f lavfi -i "color=black:size=64x64:duration=0.04" \
  -frames:v 1 -c:v h264_nvenc -f null -
# Exit 0 = encoder works. Non-zero with "Cannot load nvcuda.dll"
# = CUDA runtime missing, switch to libx264.
```

## When to flip to 720p

1080p is overkill for sleep-learning content. The viewer is
half-asleep on a phone or a bedroom TV at arm's length, and the
ambient bed and the voice dominate perception. 720p gives the
same viewing experience at 4x less memory for the filter graph
and ~2x less encode time. Flip the `output_preset` to
`sleep_720p` in the GUI Render tab or in `.sleep_learning_engine.toml`.

## When to add RAM instead

If you are on 8 GB total and want to keep the 1080p + medium
preset path, the cleanest upgrade is to 16 GB. A single 8 GB
DDR3/DDR4 SODIMM costs ~$15 and the install takes 5 minutes.
The encode time at 1080p + medium also drops ~30% with the
extra memory headroom because ffmpeg stops contending with the
OS page cache.

## When to use Colab

The cloud path is the right answer when the local box has 8 GB
of total RAM, when the OS is hogging 6+ GB, and when closing
Chrome is not an option. See [CLOUD_RENDER.md](CLOUD_RENDER.md)
for the full walkthrough.
