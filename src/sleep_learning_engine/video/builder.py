"""FFmpeg-based video builder.

Stages
------
1. Prepare a background loop: either pad an image, or trim + loop a clip.
2. Build a silent WAV the length of the runtime so the visual layer has a
   deterministic duration.
3. Encode the final video: video + audio + progress bar overlay in a single
   ffmpeg invocation, using NVENC/QSV/AMF when available.

The progress bar is drawn frame-by-frame via the ``drawtext`` filter reading
the current PTS, which keeps it perfectly in sync with the timeline.
"""

from __future__ import annotations

import json
import re
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..config import OutputPreset
from ..core import DependencyMissingError, RenderError
from ..utils.logging import get_logger
from .timing import TimingPlan

log = get_logger()


@dataclass(frozen=True)
class VideoSpec:
    """Inputs to the video builder."""

    visual_path: Path
    visual_kind: str  # "image" or "video".
    mixed_audio_path: Path
    output_path: Path
    timing: TimingPlan
    ffmpeg_bin: Path
    hardware_accel: str = "auto"  # "auto" | "nvenc" | "qsv" | "amf" | "libx264"
    render_threads: int = 0
    preset: OutputPreset = OutputPreset.SLEEP_720P


@dataclass(frozen=True)
class HardwareChoice:
    encoder: str
    extra_flags: tuple[str, ...]


def _verify_encoder_works(ffmpeg_bin: Path, encoder: str) -> bool:
    """Canary-encode a short black clip to confirm the encoder initializes.

    ffmpeg can list ``h264_nvenc`` as an encoder even when the CUDA
    runtime is not installed (no ``nvcuda.dll`` on Windows, no
    ``libcuda.so`` on Linux). The probe then fails at init time with
    "Cannot load nvcuda.dll" after the user has already waited minutes
    for TTS + mix. This helper runs a one-second canary so we catch
    the failure at hardware-pick time, not 5 minutes later.

    The probe uses 256x256. NVENC's H.264 encoder rejects any frame
    whose width OR height is below 145 px (NV_ENC_CAPS_WIDTH_MIN /
    NV_ENC_CAPS_HEIGHT_MIN; ref FFmpeg trac #9251, where 144x144 fails
    and 145x145 succeeds) with "Frame Dimension less than the minimum
    supported value". The earlier 64x64 and 128x128 probes were BOTH
    under that floor, so the canary failed on perfectly healthy NVENC
    hardware (e.g. a Colab T4) and the pipeline fell back to libx264.
    256x256 clears the floor with margin and is still tiny to encode.
    The real encodes (720p/1080p) are always far above the floor, so
    this only ever mattered for the canary, never the actual render.

    We also pass one full second at 24 fps (24 frames - enough for
    B-frame reordering) and explicit ``-pix_fmt yuv420p`` (H.264
    baseline expects it; some encoders default to a format their own
    probe path cannot handle).
    """
    cmd = [
        str(ffmpeg_bin),
        "-y",
        "-hide_banner",
        "-loglevel", "error",
        "-f", "lavfi",
        "-i", "color=black:size=256x256:rate=24:duration=1",
        "-c:v", encoder,
        "-pix_fmt", "yuv420p",
        "-bf", "0",  # no B-frames in the canary; simpler for the probe
        "-f", "null",
        "-",
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log.warning("Canary encode for {} failed to launch: {}", encoder, exc)
        return False
    if result.returncode != 0:
        # Surface only the meaningful tail of the error, not the
        # ffmpeg version banner.
        tail = "\n".join(
            line for line in result.stderr.splitlines() if "configuration" not in line
        )[-300:]
        log.warning("Canary encode for {} failed: {}", encoder, tail.strip())
        return False
    return True


def pick_hardware(choice: str, ffmpeg_bin: Path) -> HardwareChoice:
    """Select an encoder. Probes the binary if ``choice`` is ``auto``.

    The auto path goes through every HW encoder in priority order
    (NVENC, QuickSync, AMF) and picks the first one that survives a
    canary encode. Encoders that ffmpeg lists but cannot actually
    initialize (e.g. NVENC without the CUDA runtime) are skipped.
    """
    libx264 = HardwareChoice(
        "libx264",
        # `veryfast` keeps reference-frame memory low; on a 7-8 GB Windows
        # box the default `medium` preset OOMs the filter graph for 1080p
        # because the lookahead + bframes pool is too large.
        ("-preset", "ultrafast", "-crf", "22", "-tune", "zerolatency"),
    )
    if choice and choice != "auto":
        mapping = {
            "nvenc": HardwareChoice("h264_nvenc", ("-preset", "p4", "-rc", "vbr", "-b:v", "4M")),
            "qsv": HardwareChoice("h264_qsv", ("-preset", "medium", "-b:v", "4M")),
            "amf": HardwareChoice("h264_amf", ("-quality", "balanced", "-b:v", "4M")),
            "libx264": libx264,
        }
        return mapping.get(choice, libx264)

    # Probe encoders.
    try:
        result = subprocess.run(
            [str(ffmpeg_bin), "-hide_banner", "-encoders"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        encoders = result.stdout
    except (subprocess.TimeoutExpired, FileNotFoundError) as exc:
        log.warning("Could not probe encoders ({}). Falling back to libx264.", exc)
        return libx264

    if "h264_nvenc" in encoders and _verify_encoder_works(ffmpeg_bin, "h264_nvenc"):
        return HardwareChoice("h264_nvenc", ("-preset", "p4", "-rc", "vbr", "-b:v", "4M"))
    if "h264_qsv" in encoders and _verify_encoder_works(ffmpeg_bin, "h264_qsv"):
        return HardwareChoice("h264_qsv", ("-preset", "medium", "-b:v", "4M"))
    if "h264_amf" in encoders and _verify_encoder_works(ffmpeg_bin, "h264_amf"):
        return HardwareChoice("h264_amf", ("-quality", "balanced", "-b:v", "4M"))
    return libx264


# ------------------------------------------------------------- progress bar (removed)
# The previous version painted a green time-synced bar over the video
# using geq on a 1x6 strip overlaid on the background. The user asked
# us to drop it ("the progress bar is a detail, I just want the file")
# so the build pipeline no longer has to do the strip composition, the
# overlay, and the 30x speedup dance that came with it. The video
# output is now identical to the background, which is what the user
# wanted.


# ------------------------------------------------------------- main builder


def _run_encode(cmd: list[str], total_seconds: float) -> subprocess.CompletedProcess[str]:
    """Run an ffmpeg encode and return when it finishes.

    Design note: previous versions of this function streamed a coarse
    percentage via Popen + threaded stderr drain + for-line-in-stdout.
    That design produced three real bugs in production:

    1. ``th.join(timeout=2)`` deadlocked whenever ffmpeg emitted any
       warning to stderr after ``progress=end``. The cell sat at
       100% forever.
    2. The ``for line in proc.stdout`` loop never returned if ffmpeg
       had an open file handle (e.g. an unwritten trailer) keeping
       its stdout pipe from closing. Same symptom: cell at 100% forever.
    3. The first three canary encodes sometimes leaked zombie
       processes that pinned the GPU and made the next render fail
       with a confusing "driver busy" error.

    All three bugs disappeared when the user said: "the progress bar
    is a detail, I just want the file". The new implementation:

    - ``subprocess.run`` with ``capture_output=True`` (no threads, no
      pipes, no ``for line`` loop). ffmpeg's stdout/stderr are
      buffered until exit, then returned in one shot. This is what
      the user implicitly asked for.
    - ``timeout=total_seconds * 2 + 300`` so a hung ffmpeg surfaces
      as ``TimeoutExpired`` instead of an invisible cell hang.
    - No live percentage. Two log lines: one at the start, one at
      the end. The user has explicitly asked for the file, not a
      progress bar. Status text in the GUI (stage labels) is
      driven by RenderEvent callbacks from the pipeline, not by
      parsing ffmpeg's -progress stream.
    """
    timeout = max(60, int(total_seconds * 2 + 300))
    log.info("Encoding: starting (estimated {:.0f}s, hard timeout {}s)", total_seconds, timeout)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )
    log.info("Encoding: done (returncode={}, {}s of stderr)", result.returncode, len(result.stderr))
    return result


def build(spec: VideoSpec) -> Path:
    """Render the final MP4 and return its path."""
    if not spec.ffmpeg_bin.exists():
        raise DependencyMissingError(f"ffmpeg binary not found: {spec.ffmpeg_bin}")
    if not spec.visual_path.exists():
        raise RenderError(f"Visual asset missing: {spec.visual_path}")
    if not spec.mixed_audio_path.exists():
        raise RenderError(f"Mixed audio missing: {spec.mixed_audio_path}")

    spec.output_path.parent.mkdir(parents=True, exist_ok=True)
    width, height = _resolve_dimensions(spec)
    duration = spec.timing.total_seconds

    # Simple video filter: scale the background to the preset dimensions.
    # The user's content is just a still image (or looping video) over the
    # audio track. No compositing, no overlay, no progress strip.
    if spec.visual_kind == "image":
        bg_vf = _image_filter(width, height, duration)
    else:
        bg_vf = _video_filter(width, height, duration)

    hw = pick_hardware(spec.hardware_accel, spec.ffmpeg_bin)
    cmd: list[str] = [
        str(spec.ffmpeg_bin),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
    ]
    if spec.render_threads > 0:
        cmd += ["-threads", str(spec.render_threads)]
    cmd += ["-i", str(spec.visual_path)]
    cmd += ["-i", str(spec.mixed_audio_path)]

    cmd += [
        "-filter_complex",
        f"[0:v]{bg_vf},format=yuv420p[v]",
        "-map", "[v]",
        "-map", "1:a",
        "-c:v", hw.encoder,
        *hw.extra_flags,
        "-pix_fmt", "yuv420p",
        "-r", str(spec.timing.fps),
        "-t", f"{duration:.3f}",
        "-c:a", "aac",
        "-b:a", "160k",
        "-movflags", "+faststart",
        "-shortest",
        str(spec.output_path),
    ]

    log.debug("ffmpeg build command: {}", " ".join(shlex.quote(str(c)) for c in cmd))
    result = _run_encode(cmd, spec.timing.total_seconds)
    if result.returncode != 0:
        # Last-chance defence: if the user picked 'auto' and the chosen
        # HW encoder failed at init (e.g. nvcuda.dll missing after a
        # driver update), retry once with libx264 so a 5-minute render
        # does not die on the final step.
        if spec.hardware_accel == "auto" and hw.encoder != "libx264":
            tail = "\n".join(
                line for line in result.stderr.splitlines()
                if "configuration" not in line
            )[-300:]
            log.warning(
                "Encoder {} failed at init: {}. Retrying with libx264.",
                hw.encoder, tail.strip(),
            )
            libx264 = HardwareChoice("libx264", ("-preset", "ultrafast", "-crf", "22", "-tune", "zerolatency"))
            for i, token in enumerate(cmd):
                if token == "-c:v":
                    cmd[i + 1] = libx264.encoder
                    cmd[i + 2 : i + 2 + len(libx264.extra_flags)] = libx264.extra_flags
                    break
            log.debug("ffmpeg build (fallback libx264) command: {}",
                      " ".join(shlex.quote(str(c)) for c in cmd))
            result = _run_encode(cmd, spec.timing.total_seconds)
            if result.returncode == 0:
                log.warning("Fallback to libx264 succeeded; final render OK.")
        if result.returncode != 0:
            log.error("ffmpeg render failed: {}", result.stderr[-2000:])
            raise RenderError(f"ffmpeg exited with code {result.returncode}.")
    if not spec.output_path.exists() or spec.output_path.stat().st_size == 0:
        raise RenderError("ffmpeg produced an empty output file.")
    log.info("Render complete: {}", spec.output_path)
    return spec.output_path


def _resolve_dimensions(spec: VideoSpec) -> tuple[int, int]:
    if spec.preset is OutputPreset.SLEEP_1080P:
        return 1920, 1080
    if spec.preset is OutputPreset.AUDIO_ONLY:
        return 1280, 720
    if spec.preset is OutputPreset.SLEEP_720P:
        return 1280, 720
    return 1280, 720


# ------------------------------------------------------ background streams


def _image_filter(width: int, height: int, duration: float) -> str:
    """Filter for a still image stretched to fill the target dimensions."""
    return (
        f"loop=loop=-1:size=1:start=0,"
        f"trim=duration={duration:.3f},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"setsar=1,fps=24"
    )


def _video_filter(width: int, height: int, duration: float) -> str:
    """Filter for a looping video background that fills the target dimensions."""
    return (
        f"loop=loop=-1:size=1:start=0,"
        f"trim=duration={duration:.3f},"
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"setsar=1,fps=24"
    )


# ----------------------------------------------------- progress reporter (removed)
# The GUI used to call ``run_with_progress(cmd, on_progress=...)`` to
# paint a live progress widget while ffmpeg ran. That function used
# Popen + a for-line-in-stdout loop, which has the same deadlock
# potential as _run_encode used to. The GUI now just calls the regular
# encode path and shows a static 'Rendering... please wait' label;
# when the subprocess returns, the label flips to 'Done' or 'Failed'.
# The Popen streaming code is gone entirely - the GUI and the CLI now
# share the same subprocess.run-based path.
