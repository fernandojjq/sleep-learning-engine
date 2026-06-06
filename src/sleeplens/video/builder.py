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


def pick_hardware(choice: str, ffmpeg_bin: Path) -> HardwareChoice:
    """Select an encoder. Probes the binary if ``choice`` is ``auto``."""
    if choice and choice != "auto":
        mapping = {
            "nvenc": HardwareChoice("h264_nvenc", ("-preset", "p4", "-rc", "vbr", "-b:v", "4M")),
            "qsv": HardwareChoice("h264_qsv", ("-preset", "medium", "-b:v", "4M")),
            "amf": HardwareChoice("h264_amf", ("-quality", "balanced", "-b:v", "4M")),
            "libx264": HardwareChoice("libx264", ("-preset", "medium", "-crf", "20")),
        }
        return mapping.get(choice, mapping["libx264"])

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
        return HardwareChoice("libx264", ("-preset", "medium", "-crf", "20"))

    if "h264_nvenc" in encoders:
        return HardwareChoice("h264_nvenc", ("-preset", "p4", "-rc", "vbr", "-b:v", "4M"))
    if "h264_qsv" in encoders:
        return HardwareChoice("h264_qsv", ("-preset", "medium", "-b:v", "4M"))
    if "h264_amf" in encoders:
        return HardwareChoice("h264_amf", ("-quality", "balanced", "-b:v", "4M"))
    return HardwareChoice("libx264", ("-preset", "medium", "-crf", "20"))


# ------------------------------------------------------------- progress bar


def _normalise_color(color: str) -> str:
    match = HEX_COLOR.match(color.strip())
    if not match:
        log.warning("Invalid progress bar color '{}'. Using #00FF00.", color)
        return PROGRESS_BAR_DEFAULT_COLOR
    return f"0x{match.group(1).upper()}"


def _progress_filter(
    *,
    width: int,
    height: int,
    bar_height: int,
    position: str,
    color_hex: str,
    frame_count: int,
) -> str:
    """Build the ``geq`` filter that paints a frame-synced progress bar.

    drawbox's expression scope does not include the frame number, so the
    bar width cannot be animated per-frame with drawbox alone. ``geq`` does
    expose ``N`` (current frame index) and the pixel-level coordinates
    ``X`` / ``Y`` plus image dimensions ``W`` / ``H``, which is exactly
    what a per-pixel progress bar needs.
    """
    y_top = (height - bar_height - 4) if position == "bottom" else 4
    y_bot = y_top + bar_height
    n = max(1, int(frame_count))
    r, g, b = _hex_to_rgb(color_hex)
    # Order matters: the dark track first, then the green fill on top.
    # We use geq to paint the green strip where X < W*N/n, only on the bar
    # rows, so the rest of the frame is left untouched.
    return (
        f"format=rgb24,"
        f"drawbox=x=0:y={y_top}:w=iw:h={bar_height}:color=black@0.55:t=fill,"
        f"geq=r='if(between(Y\\,{y_top}\\,{y_bot})\\,"
        f"if(lt(X\\,W*N/{n})\\,{r}\\,r(X\\,Y))\\,r(X\\,Y))':"
        f"g='if(between(Y\\,{y_top}\\,{y_bot})\\,"
        f"if(lt(X\\,W*N/{n})\\,{g}\\,g(X\\,Y))\\,g(X\\,Y))':"
        f"b='if(between(Y\\,{y_top}\\,{y_bot})\\,"
        f"if(lt(X\\,W*N/{n})\\,{b}\\,b(X\\,Y))\\,b(X\\,Y))'"
    )


def _hex_to_rgb(color_hex: str) -> tuple[int, int, int]:
    h = color_hex.lstrip("#")
    if len(h) == 6:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    if len(h) == 8:
        return int(h[2:4], 16), int(h[4:6], 16), int(h[6:8], 16)
    return 0, 255, 0  # default to #00FF00


# ------------------------------------------------------------- main builder


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

    progress_filter = _progress_filter(
        width=width,
        height=height,
        bar_height=spec.progress_height,
        position=spec.progress_position,
        color_hex=color,
        frame_count=spec.timing.frame_count,
    )

    filter_complex = f"[0:v]{bg_input['vf']},{progress_filter},format=yuv420p[v]"
    if "af" in bg_input:
        filter_complex += f";{bg_input['af']}[a]"

    hw = pick_hardware(spec.hardware_accel, spec.ffmpeg_bin)
    cmd: list[str] = [
        str(spec.ffmpeg_bin),
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",
        "-stats",
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
    result = subprocess.run(cmd, capture_output=True, text=True)
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
