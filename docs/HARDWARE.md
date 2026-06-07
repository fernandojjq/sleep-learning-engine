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

`auto` runs a one-second canary encode for each candidate (NVENC,
QSV, AMF) in order. The first one that initializes successfully
wins. ffmpeg's `h264_nvenc` entry in `-encoders` proves the encoder
is **compiled in**, not that it can **initialize** - the canary
catches the case where the CUDA runtime is missing or the driver
is too old. On a 8 GB Windows laptop with no discrete GPU, the
canary chain falls through to `libx264`.

If the chosen HW encoder also fails at full encode time (rare, but
some Intel QSV builds pass the canary on software emulation and
then choke at scale), the build retries once with `libx264` and
surfaces a warning in the log.

### NVENC H.264 minimum dimension (145 px)

NVENC's H.264 encoder enforces a hard minimum of 145 pixels per
axis (the `NV_ENC_CAPS_WIDTH_MIN` / `NV_ENC_CAPS_HEIGHT_MIN`
caps). A frame whose width OR height is below 145 px is rejected
at init with:

```
[h264_nvenc @ 0x...] InitializeEncoder failed: invalid param (8):
Frame Dimension less than the minimum supported value.
```

The reference is FFmpeg trac ticket #9251, where 144x144 fails
and 145x145 succeeds. The canary in `_verify_encoder_works`
therefore uses `size=256x256:rate=24:duration=1` - comfortably
above the floor with margin, and still tiny to encode. The real
project renders (720p / 1080p) are always far above the floor, so
this constraint only ever affects the canary probe itself, never
the actual video.

Do not shrink the canary below 256x256. 64x64 and 128x128 both
trigger the floor and the canary will then reject perfectly
healthy NVENC hardware, sending the pipeline to the much slower
`libx264` fallback.

## Verifying your setup

```bash
# List available encoders.
uv run cache/ffmpeg.exe -hide_banner -encoders | findstr h264

# Canary-style probe. Replace the encoder name with yours.
uv run cache/ffmpeg.exe -y -hide_banner -loglevel error \
  -f lavfi -i "color=black:size=256x256:rate=24:duration=1" \
  -c:v h264_nvenc -pix_fmt yuv420p -bf 0 -f null -
# Exit 0 = encoder works. Non-zero with "Cannot load nvcuda.dll"
# = CUDA runtime missing, switch to libx264.
# Non-zero with "Frame Dimension less than the minimum" = probe
# is below the 145 px NVENC minimum, bump size up.
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
