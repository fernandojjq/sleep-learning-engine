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

PROGRESS_BAR_DEFAULT_COLOR = "#00FF00"
HEX_COLOR = re.compile(r"^#?([0-9A-Fa-f]{6})$")


@dataclass(frozen=True)
class VideoSpec:
    """Inputs to the video builder."""

    visual_path: Path
    visual_kind: str  # "image" or "video".
    mixed_audio_path: Path
    output_path: Path
    timing: TimingPlan
    ffmpeg_bin: Path
    progress_color: str = PROGRESS_BAR_DEFAULT_COLOR
    progress_height: int = 6
    progress_position: str = "bottom"  # "top" or "bottom".
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


# ------------------------------------------------------------- progress bar


def _normalise_color(color: str) -> str:
    match = HEX_COLOR.match(color.strip())
    if not match:
        log.warning("Invalid progress bar color '{}'. Using #00FF00.", color)
        return PROGRESS_BAR_DEFAULT_COLOR
    return f"0x{match.group(1).upper()}"


def _progress_filter(
    *,
    bg_vf: str,
    width: int,
    height: int,
    bar_height: int,
    position: str,
    color_hex: str,
    total_seconds: float,
    fps: int,
) -> str:
    """Compose the full video filtergraph: background + a time-synced bar.

    The progress bar is painted with ``geq`` on a *tiny fixed-size strip*
    (``width`` x ``bar_height``), then overlaid onto the background.

    The previous version ran ``geq`` per-pixel over the ENTIRE 720p/1080p
    frame for every one of ~10k frames. ``geq`` evaluates its expression once
    per output pixel, single-threaded, on the CPU (NVENC never touches the
    filter graph), so a 7-minute 1080p render spent ~25-40 min just in the
    progress filter and looked completely frozen. Restricting geq to the
    ~1280x6 bar strip is ~30x faster and pixel-identical on screen.

    geq exposes ``T`` (timestamp) and per-pixel ``X`` / ``W``; the strip is
    the fill colour where ``X < W*T/total`` and a dark track otherwise.
    (drawbox cannot do this: its x/y/w/h expressions only expose geometric
    constants - no time or frame index - which is the whole reason geq is
    needed for an animated width.)
    """
    y_top = (height - bar_height - 4) if position == "bottom" else 4
    dur = max(0.001, float(total_seconds))
    h = color_hex.lower().lstrip("#")
    if h.startswith("0x"):
        h = h[2:]
    h = h[-6:].rjust(6, "0")
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    thr = f"W*T/{dur:.3f}"  # progress fraction, in pixels, at time T
    strip = (
        f"color=c=black:s={width}x{bar_height}:r={fps}:d={dur:.3f},format=gbrp,"
        f"geq=r='if(lt(X\\,{thr})\\,{r}\\,30)':"
        f"g='if(lt(X\\,{thr})\\,{g}\\,30)':"
        f"b='if(lt(X\\,{thr})\\,{b}\\,30)'[bar]"
    )
    return (
        f"{strip};"
        f"[0:v]{bg_vf}[bg];"
        f"[bg][bar]overlay=x=0:y={y_top}:shortest=1,format=yuv420p[v]"
    )


def _hex_to_rgb(color_hex: str) -> tuple[int, int, int]:
    h = color_hex.lstrip("#")
    if len(h) == 6:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if len(h) == 8:
        return int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
    return 0, 255, 0  # default to #00FF00


# ------------------------------------------------------------- main builder


def _run_encode(cmd: list[str], total_seconds: float) -> subprocess.CompletedProcess[str]:
    """Run an ffmpeg encode while streaming a coarse percentage.

    ``build`` previously ran the encode with ``subprocess.run(...,
    capture_output=True)``, which buffers all output until ffmpeg exits, so
    the encode step printed nothing and looked hung for its entire duration.
    Here we read ffmpeg's ``-progress -`` key/value stream from stdout and log
    one line every 10% (newline-terminated, so it streams through a
    line-buffered parent such as the Colab cell). stderr is drained on a
    thread to avoid a pipe-fill deadlock and returned for the fallback path.
    """
    import threading

    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
    )
    err: list[str] = []

    def _drain() -> None:
        assert proc.stderr is not None
        for ln in proc.stderr:
            err.append(ln)

    th = threading.Thread(target=_drain, daemon=True)
    th.start()

    total = max(0.001, float(total_seconds))
    last_bucket = -1
    assert proc.stdout is not None
    try:
        for line in proc.stdout:
            line = line.strip()
            if line.startswith(("out_time_us=", "out_time_ms=")):
                try:
                    raw = int(line.split("=", 1)[1])
                except ValueError:
                    continue
                secs = raw / (1_000_000 if "us=" in line else 1_000)
                pct = min(100, int(secs / total * 100))
                bucket = pct - (pct % 10)
                if bucket > last_bucket:
                    last_bucket = bucket
                    log.info("Encoding: {}% ({:.0f}/{:.0f}s)", bucket, secs, total)
            elif line == "progress=end" and last_bucket < 100:
                last_bucket = 100
                log.info("Encoding: 100% ({:.0f}/{:.0f}s)", total, total)
    finally:
        # CRITICAL: wait for the stderr drain thread to fully consume
        # the stderr pipe BEFORE we let the process exit. If we don't,
        # ffmpeg blocks on a full stderr pipe and the whole render hangs
        # at 100% forever. The previous version had `th.join(timeout=2)`
        # which was a guaranteed deadlock on a busy ffmpeg that emits
        # any warning to stderr after the progress=end marker.
        proc.wait()
        th.join()  # no timeout: the pipe is bounded by ffmpeg's lifetime
    return subprocess.CompletedProcess(
        cmd, proc.returncode, stdout="", stderr="".join(err)
    )


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
    color = _normalise_color(spec.progress_color)

    # Build the background stream.
    if spec.visual_kind == "image":
        bg_input = _build_image_stream(spec.visual_path, spec.timing.total_seconds, width, height)
    else:
        bg_input = _build_video_stream(spec.visual_path, spec.timing.total_seconds, width, height)

    filter_complex = _progress_filter(
        bg_vf=bg_input["vf"],
        width=width,
        height=height,
        bar_height=spec.progress_height,
        position=spec.progress_position,
        color_hex=color,
        total_seconds=spec.timing.total_seconds,
        fps=spec.timing.fps,
    )
    if "af" in bg_input:
        filter_complex += f";{bg_input['af']}[a]"

    hw = pick_hardware(spec.hardware_accel, spec.ffmpeg_bin)
    cmd: list[str] = [
        str(spec.ffmpeg_bin),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-progress",
        "-",
    ]
    if spec.render_threads > 0:
        cmd += ["-threads", str(spec.render_threads)]
    cmd += ["-i", str(spec.visual_path if spec.visual_kind == "image" else spec.visual_path)]
    cmd += ["-i", str(spec.mixed_audio_path)]

    cmd += [
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
    ]
    if "af" in bg_input:
        cmd += ["-map", "[a]"]
    else:
        cmd += ["-map", "1:a"]
    cmd += [
        "-c:v",
        hw.encoder,
        *hw.extra_flags,
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(spec.timing.fps),
        "-t",
        f"{spec.timing.total_seconds:.3f}",
        "-c:a",
        "aac",
        "-b:a",
        "160k",
        "-movflags",
        "+faststart",
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


def _build_image_stream(image: Path, duration: float, width: int, height: int) -> dict[str, str]:
    return {
        "vf": (
            f"loop=loop=-1:size=1:start=0,"
            f"trim=duration={duration:.3f},"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"setsar=1,fps=24"
        ),
    }


def _build_video_stream(video: Path, duration: float, width: int, height: int) -> dict[str, str]:
    return {
        "vf": (
            f"loop=loop=-1:size=1:start=0,"
            f"trim=duration={duration:.3f},"
            f"scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height},"
            f"setsar=1,fps=24"
        ),
    }


# ----------------------------------------------------- progress reporter


def run_with_progress(cmd: list[str], on_progress) -> subprocess.CompletedProcess[str]:
    """Run a subprocess that emits ``-progress -`` key=value pairs.

    Each line is forwarded to ``on_progress(time_us, speed)`` so the GUI can
    paint a live status indicator.
    """
    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
    )
    time_us = 0
    speed = 0.0
    assert process.stdout is not None
    for line in process.stdout:
        line = line.strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key == "out_time_us":
            try:
                time_us = int(value)
            except ValueError:
                pass
        elif key == "speed":
            try:
                speed = float(value.rstrip("x"))
            except ValueError:
                pass
        on_progress(time_us / 1_000_000, speed)
    stderr = process.stderr.read() if process.stderr else ""
    process.wait()
    return subprocess.CompletedProcess(cmd, process.returncode, stdout="", stderr=stderr)


# silence the unused import warnings for json/re (kept for future extensions).
_ = json, re
