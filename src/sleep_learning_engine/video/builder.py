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
    progress_bar_avatar: str = ""


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
def _progress_filter(
    width: int,
    height: int,
    frame_count: float,
    fps: float,
) -> str:
    """Return the filter graph to draw a stylish progress bar in the bottom-left corner.

    The bar is 300px wide, 6px high, positioned 50px from the left and 80px above
    the bottom to avoid the YouTube playback control overlay.
    """
    bar_width = 300
    bar_height = 6
    x_start = 50
    y_top = height - 80

    duration = max(1.0, frame_count / fps)

    # Use a dynamic scale filter (eval=frame) and overlay to draw the moving progress bar
    # at high speed, avoiding the slow CPU-bound geq or static drawbox evaluation.
    # We specify :r={fps} on the color source to synchronize frame rates and keep progress in sync.
    # We add a 1px grey border around the black background track to make its limits visible.
    return (
        f"drawbox=x={x_start}:y={y_top}:w={bar_width}:h={bar_height}:color=black@0.55:t=fill,"
        f"drawbox=x={x_start-1}:y={y_top-1}:w={bar_width+2}:h={bar_height+2}:color=gray@0.40:t=1[bg];"
        f"color=c=green:s={bar_width}x{bar_height}:r={fps}[bar];"
        f"[bar]scale=w='max(t/{duration:.3f}*{bar_width},1)':h={bar_height}:eval=frame[scaled_bar];"
        f"[bg][scaled_bar]overlay=x={x_start}:y={y_top}:shortest=1"
    )


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


def _find_avatar_logo() -> Path | None:
    """Find the channel's avatar logo in the standard YouTube assets directories."""
    possible_paths = [
        Path(r"D:\Youtube\sleepingdevfer34\Sleeping Dev\logo_sleeping_dev.jpeg"),
        Path(r"D:\Youtube\sleepingdevfer34\Geopolitical sandbox\logo.png"),
        Path(r"D:\Youtube\sleepingdevfer34\Sleeping scientists\personalizacion\Logo.png"),
    ]
    for p in possible_paths:
        if p.exists():
            return p
    return None


def _draw_wrapped_text(draw, text, font, max_width, start_x, start_y, line_spacing=4):
    """Draw text with word wrapping, truncating to 2 lines max with ellipsis if necessary."""
    words = text.split(" ")
    lines = []
    current_line = []

    for word in words:
        test_line = " ".join(current_line + [word])
        # Get width of test line
        bbox = draw.textbbox((0, 0), test_line, font=font)
        w = bbox[2] - bbox[0]
        if w <= max_width:
            current_line.append(word)
        else:
            if current_line:
                lines.append(" ".join(current_line))
                current_line = [word]
            else:
                lines.append(word)
                current_line = []
    if current_line:
        lines.append(" ".join(current_line))

    # Truncate to 2 lines and add ellipsis if needed
    if len(lines) > 2:
        second_line = lines[1]
        while len(second_line) > 3 and draw.textbbox((0, 0), second_line + "...", font=font)[2] - draw.textbbox((0, 0), second_line + "...", font=font)[0] > max_width:
            words_in_second = second_line.split(" ")
            if len(words_in_second) > 1:
                second_line = " ".join(words_in_second[:-1])
            else:
                second_line = second_line[:-1]
        lines = [lines[0], second_line + "..."]

    y = start_y
    for line in lines:
        draw.text((start_x, y), line, font=font, fill=(255, 255, 255, 255))
        bbox = draw.textbbox((0, 0), line, font=font)
        h = bbox[3] - bbox[1]
        y += h + line_spacing
    return y


def _generate_player_card(
    card_path: Path,
    bar_path: Path,
    title_text: str,
    duration_seconds: float,
    avatar_path: str = "",
):
    """Generate a premium translucent music player card PNG (containing avatar, title,
    progress track, and total duration) and a matching lime green progress bar PNG.
    """
    try:
        from PIL import Image, ImageDraw, ImageFont, ImageOps
    except ImportError as exc:
        raise DependencyMissingError("Pillow is required to generate player card images.") from exc

    card_path.parent.mkdir(parents=True, exist_ok=True)

    # Card dimensions
    card_w, card_h = 750, 140

    # 1. Base card image (translucent dark slate background with a subtle border)
    card_img = Image.new("RGBA", (card_w, card_h), (0, 0, 0, 0))
    card_draw = ImageDraw.Draw(card_img)
    card_draw.rounded_rectangle(
        [(0, 0), (card_w - 1, card_h - 1)],
        radius=24,
        fill=(15, 15, 20, 190),       # Translucent dark slate background
        outline=(255, 255, 255, 35),  # Subtle light white/grey border
        width=1
    )

    # 2. Load and overlay Avatar
    avatar_w, avatar_h = 100, 100
    avatar_x, avatar_y = 20, 20

    logo_path = None
    if avatar_path:
        p = Path(avatar_path)
        if p.exists():
            logo_path = p
        else:
            log.warning("Specified progress bar avatar does not exist: {}. Falling back to default logo search.", avatar_path)
            logo_path = _find_avatar_logo()
    else:
        logo_path = _find_avatar_logo()

    if logo_path:
        try:
            avatar_img = Image.open(logo_path).convert("RGBA")
            avatar_img = ImageOps.fit(avatar_img, (avatar_w, avatar_h), Image.Resampling.LANCZOS)

            # Apply rounded corners to avatar
            mask = Image.new("L", (avatar_w, avatar_h), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.rounded_rectangle([(0, 0), (avatar_w - 1, avatar_h - 1)], radius=16, fill=255)
            avatar_img.putalpha(mask)

            card_img.alpha_composite(avatar_img, (avatar_x, avatar_y))
        except Exception as e:
            log.warning("Failed to load/process avatar logo from {}: {}", logo_path, e)
            logo_path = None

    if not logo_path:
        # Draw a beautiful placeholder avatar if no logo is found
        avatar_draw_img = Image.new("RGBA", (avatar_w, avatar_h), (0, 0, 0, 0))
        avatar_draw = ImageDraw.Draw(avatar_draw_img)
        avatar_draw.rounded_rectangle(
            [(0, 0), (avatar_w - 1, avatar_h - 1)],
            radius=16,
            fill=(30, 41, 59, 255),       # Slate-800
            outline=(255, 255, 255, 50),
            width=1
        )
        try:
            ph_font = ImageFont.truetype("/Windows/Fonts/arialbd.ttf", 36)
        except Exception:
            ph_font = ImageFont.load_default()

        ph_text = "SD"
        bbox = avatar_draw.textbbox((0, 0), ph_text, font=ph_font)
        tx = (avatar_w - (bbox[2] - bbox[0])) // 2
        ty = (avatar_h - (bbox[3] - bbox[1])) // 2 - 2
        avatar_draw.text((tx, ty), ph_text, font=ph_font, fill=(255, 255, 255, 200))
        card_img.alpha_composite(avatar_draw_img, (avatar_x, avatar_y))

    # 3. Load fonts
    try:
        font_title = ImageFont.truetype("/Windows/Fonts/arialbd.ttf", 20)
        font_time = ImageFont.truetype("/Windows/Fonts/arial.ttf", 14)
    except Exception:
        font_title = ImageFont.load_default()
        font_time = ImageFont.load_default()

    # 4. Draw wrapped Title text
    title_start_x = 140
    title_start_y = 18
    max_title_width = 590
    _draw_wrapped_text(card_draw, title_text, font_title, max_title_width, title_start_x, title_start_y, line_spacing=4)

    # 5. Draw Progress Track
    track_x = 140
    track_y = 82
    track_w = 570
    track_h = 10
    card_draw.rounded_rectangle(
        [(track_x, track_y), (track_x + track_w - 1, track_y + track_h - 1)],
        radius=5,
        fill=(30, 30, 38, 255),       # Dark slate track background
        outline=(60, 60, 75, 255),    # Soft track border
        width=1
    )

    # 6. Draw Total Duration text on the right side under the track
    h_val, rem = divmod(int(duration_seconds), 3600)
    m_val, s_val = divmod(rem, 60)
    duration_str = f"{h_val:02d}:{m_val:02d}:{s_val:02d}"

    bbox = card_draw.textbbox((0, 0), duration_str, font=font_time)
    duration_w = bbox[2] - bbox[0]
    duration_x = track_x + track_w - duration_w
    duration_y = 104
    card_draw.text((duration_x, duration_y), duration_str, font=font_time, fill=(255, 255, 255, 180))

    # Save player card image
    card_img.save(card_path, "PNG")

    # 7. Generate matching progress bar image
    bar_img = Image.new("RGBA", (track_w, track_h), (0, 0, 0, 0))
    bar_draw = ImageDraw.Draw(bar_img)
    bar_draw.rounded_rectangle(
        [(0, 0), (track_w - 1, track_h - 1)],
        radius=5,
        fill=(118, 255, 3, 255),     # Vibrant Lime green `#76ff03`
    )
    bar_img.save(bar_path, "PNG")


def _format_duration(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h:02d}\\:{m:02d}\\:{s:02d}"
    return f"{m:02d}\\:{s:02d}"


def _escape_ffmpeg_text(text: str) -> str:
    # Escape special characters for FFmpeg's drawtext filter
    text = text.replace("\\", "\\\\")
    text = text.replace(":", "\\:")
    text = text.replace("'", "\\'")
    text = text.replace("%", "\\%")
    text = text.replace(",", "\\,")
    return text


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

    # Scale the background to the preset dimensions.
    if spec.visual_kind == "image":
        bg_vf = _image_filter(width, height, duration)
    else:
        bg_vf = _video_filter(width, height, duration)

    # Generate progress bar assets (rounded capsule styling)
    cache_dir = Path("cache")
    cache_dir.mkdir(exist_ok=True)
    track_path = cache_dir / "player_card.png"
    bar_path = cache_dir / "progress_bar.png"

    title_text = spec.output_path.name.replace(spec.output_path.suffix, "")
    _generate_player_card(track_path, bar_path, title_text, duration, spec.progress_bar_avatar)

    # Dynamic positioning relative to output resolution
    x_start = 80
    y_top = height - 200  # 140px card height leaves 60px padding at the bottom of 1080p
    time_x = x_start + 140
    time_y = y_top + 104

    filter_complex = (
        f"[0:v]{bg_vf}[bg_base];"
        f"[bg_base][2:v]overlay=x={x_start}:y={y_top}[bg_with_track];"
        f"[3:v]scale=w='max(t/{duration:.3f}*570,10)':h=10:eval=frame[scaled_bar];"
        f"[bg_with_track][scaled_bar]overlay=x={x_start+140}:y={y_top+82}:shortest=1[bg_with_bar];"
        f"[bg_with_bar]drawtext=fontfile='/Windows/Fonts/arial.ttf':text='%{{pts\\:gmtime\\:0\\:%H\\\\\\:%M\\\\\\:%S}}':x={time_x}:y={time_y}:fontcolor=white@0.70:fontsize=14:shadowcolor=black@0.4:shadowx=1:shadowy=1,format=yuv420p[v]"
    )

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
    if spec.visual_kind == "video":
        cmd += ["-stream_loop", "-1"]
    cmd += ["-i", str(spec.visual_path)]
    cmd += ["-i", str(spec.mixed_audio_path)]
    cmd += ["-loop", "1", "-i", str(track_path)]
    cmd += ["-loop", "1", "-i", str(bar_path)]

    cmd += [
        "-filter_complex",
        filter_complex,
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
        f"scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},"
        f"setsar=1,"
        f"loop=loop=-1:size=1:start=0,"
        f"trim=duration={duration:.3f},"
        f"fps=24"
    )


def _video_filter(width: int, height: int, duration: float) -> str:
    """Filter for a looping video background that fills the target dimensions."""
    return (
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
