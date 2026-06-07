# Colab Pro + NVENC: root cause identified

Date: 2026-06-07.

## What we wanted

Render a 6 minute 54 second (414.8 seconds, 9954 frames at 24 fps),
1920x1080, H.264 video with AAC audio on a **Colab Pro T4** instance,
using the T4's **NVENC** hardware encoder so the encode finishes in
1-2 minutes instead of the ~10-15 minutes libx264 would take on CPU.

## Root cause

NVENC's H.264 encoder enforces a hard minimum of 145 pixels per axis
(`NV_ENC_CAPS_WIDTH_MIN` / `NV_ENC_CAPS_HEIGHT_MIN`). The reference
is FFmpeg trac ticket #9251, where 144x144 fails with:

```
[h264_nvenc @ 0x...] InitializeEncoder failed: invalid param (8):
Frame Dimension less than the minimum supported value.
```

and 145x145 succeeds.

The canary probe in `_verify_encoder_works` (`src/sleep_learning_engine/video/builder.py`)
was using 64x64 (original) and then 128x128 (after the first fix).
**Both are below the 145 px floor.** The T4 in the Colab Pro instance
was perfectly healthy - `nvidia-smi` reported `Tesla T4, 15360 MiB`,
the NVIDIA driver was working, the LD_LIBRARY_PATH patch was applied.
NVENC was just rejecting the probe frame because of its size, not
because the encoder was broken.

That single detail (a 17 px difference between the canary and the
NVENC minimum) caused every prior "fix" to look like it didn't work.
The CUDA runtime check passed. The nvidia-smi check passed. The
LD_LIBRARY_PATH patch made the encoder list show up. The 128x128 +
1 second + yuv420p + no B-frames combo all made the canary more
realistic. None of it mattered because the dimension itself was
disqualifying.

## The fix

Bump the canary to 256x256. That clears the 145 px floor with a
111 px margin, is still tiny to encode (1 second at 24 fps = 24
frames), and the real project renders (720p, 1080p) were always
above the floor - they just never got a chance to use NVENC because
the canary gate was rejecting the encoder before the real encode
even started.

The new canary command in `_verify_encoder_works`:

```bash
ffmpeg -y -hide_banner -loglevel error \
  -f lavfi -i "color=black:size=256x256:rate=24:duration=1" \
  -c:v <encoder> -pix_fmt yuv420p -bf 0 -f null -
```

## Why the other 6 attempts looked broken

1. **Original canary (64x64, duration=0.04, -frames:v 1).**
   Way under the 145 px floor. NVENC rejected with the dimension
   error.

2. **LD_LIBRARY_PATH patch (commit `83d4874`).**
   Patched `os.environ["LD_LIBRARY_PATH"]` to include
   `/usr/lib64-nvidia` (Colab's NVIDIA lib path). This was
   necessary - without it, ffmpeg would not even find
   `libcuda.so` - but it only addresses the "Cannot load
   nvcuda.dll" failure mode, not the dimension error. Both
   failures were happening, the LD_LIBRARY_PATH fix only
   resolved the first.

3. **nvidia-smi check (commit `83d4874`).**
   Replaced the misleading "NVENC available: " line with a real
   `nvidia-smi` query. This was needed for diagnostics - it
   proved the T4 was bound to the container with 15 GB VRAM - but
   the encoder-level dimension check was downstream of this and
   unaffected.

4. **Subprocess.Popen streaming (commit `83d4874`).**
   Switched from `subprocess.run(..., capture_output=True)` to
   `subprocess.Popen` with line-buffered stdout merged with
   stderr. This fixed the "render looks frozen" symptom, but
   did not change the canary behaviour.

5. **Canary bump to 128x128 / 1s / yuv420p / no B-frames
   (commit `d8d5cb2`).**
   Better probe (1s of real frame timing, explicit pixfmt, no
   B-frames to keep the filter graph simple), but still 128x128
   is **17 px short of the 145 minimum**. The error message
   from NVENC was the same.

6. **Local render with `libx264` forced (workaround).**
   Confirmed the pipeline itself works end-to-end (1 paragraph,
   40s, 720p, 1 thread, 8.6 MB MP4 in 68.6s on the local
   Windows box) and the only blocker was the canary gate. But
   it was a workaround, not a fix - the cloud path was still
   going through libx264 and taking 10-15 min for a 6:55 video.

7. **AMF probe after NVENC fails.**
   Once NVENC was rejected, the auto path tried QSV (expected
   to fail on a non-Intel T4) and then AMF. AMF was hanging
   indefinitely on the T4 because AMD's AMF runtime is not
   designed for non-AMD hardware - some builds busy-loop
   waiting for an AMD device that will never appear. With the
   canary now passing for NVENC, AMF is never tried on T4s
   and the hang disappears.

## Verification plan

After the 256x256 canary lands:

1. Run the canary locally on a real NVENC GPU (or on Colab Pro T4)
   and confirm exit code 0.
2. Run `python -m sleep_learning_engine render ...` with
   `hardware_accel = "auto"` and confirm the log shows
   `Canary encode for h264_nvenc passed` (not failed).
3. Confirm the final encode finishes in 1-2 min for a 6:55
   1080p video on T4, not 10-15 min.
4. Confirm the studio reuses the canary-passing NVENC choice on
   the next run without re-probing (or re-probes and still picks
   it).

If the canary still fails after the bump, the next thing to check
is whether the running ffmpeg build was compiled against an
NVENC SDK older than the one in the driver. That would surface
as a different error (typically "NVENC API version mismatch")
and would be resolved by upgrading the ffmpeg static build on
the Colab notebook side, not by changing the canary again.

## Relevant files in the repo

- `src/sleep_learning_engine/video/builder.py` -
  `_verify_encoder_works` (the canary, now 256x256) and `build`
  (the encode call + libx264 retry).
- `tests/test_encoder_fallback.py` - regression tests for the
  canary path. New test added: the auto path must select NVENC
  when the canary returns True, and must include the
  `p4`/`vbr`/`4M` flag set in `HardwareChoice.extra_flags`.
- `scripts/generate_colab_notebook.py` - generator for the
  public Colab notebook.
- `scripts/generate_drive_notebook.py` - generator for the
  personal Drive-mounted notebook.
- `scripts/generate_kaggle_notebook.py` - generator for the
  Kaggle notebook.
- `docs/cloud/low_ram_render.ipynb` - public Colab notebook.
- `docs/cloud/drive_render.ipynb` - personal Drive notebook.
- `docs/cloud/kaggle_render.ipynb` - Kaggle notebook.
- `docs/HARDWARE.md` - encoder cheat sheet, with the 145 px
  minimum documented in the auto-mode section.
- `.sleeplens.toml` - user's personal config. Should be flipped
  back to `hardware_accel = "auto"` (or omitted entirely, since
  "auto" is the default) once the canary is fixed.

## Commit history relevant to this issue

- `79a8212` - Project rename (includes fallback
  `.sleeplens.toml` <-> `.sleep_learning_engine.toml`).
- `83d4874` - Three cloud-notebook fixes: nvidia-smi check,
  LD_LIBRARY_PATH patch, subprocess.Popen streaming.
- `d8d5cb2` - Canary bump from 64x64 to 128x128 / 1s / yuv420p.
  Helped with timing, did not address the dimension floor.
- `450ec04` - CHANGELOG entry for the post-rename fixes.
- `cacc2ae` - CHANGELOG entry continuing the post-rename fixes.
- `e0d2a0d` - This document (the original problem statement).
- `<next>` - The 256x256 canary fix + doc updates + regression
  test, the actual root cause resolution.

(This document describes the root cause and the path to the fix.
It does not include the diff itself; see the next commit for
that.)
