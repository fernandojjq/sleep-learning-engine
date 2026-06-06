"""End-to-end render pipeline.

The pipeline module owns the full flow:

1. Load or generate the script.
2. Render the voice track.
3. Pick and mix the ambient bed.
4. Resolve (or generate) the background visual.
5. Compute the final timing.
6. Encode the final MP4.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from ..ai.connector import AIConnector
from ..ai.script_writer import Script, ScriptWriter, load_script_from_file
from ..audio.mixer import (
    MixSpec,
    extract_script_keywords,
    mix_bed_and_voice,
    pick_ambient,
    scan_ambient_library,
)
from ..audio.tts import TTSEngine, TTSResult
from ..config import (
    AIProvider,
    AmbientMode,
    AppSettings,
    OutputPreset,
    PROVIDER_PRESETS,
    ProjectPaths,
    TTSBackend,
)
from ..core import ConfigError, SleeplensError
from ..utils.logging import get_logger
from ..video.builder import VideoSpec, build
from ..video.timing import TimingPlan, compute_timing
from ..visual.assets import VisualSource, generate_fallback, resolve_visual
from .state import RenderEvent, RenderStage, RenderStatus

log = get_logger()

ProgressCallback = Callable[[RenderEvent], None]


@dataclass
class RenderResult:
    """Summary of a completed render."""

    output_path: Path
    script: Script
    tts: TTSResult
    timing: TimingPlan
    visual: VisualSource
    duration_seconds: float
    elapsed_seconds: float
    notes: list[str] = field(default_factory=list)


# ------------------------------------------------------------------ connector


def build_connector(settings: AppSettings) -> AIConnector:
    """Construct the AI connector for the selected provider preset."""
    preset = next((p for p in PROVIDER_PRESETS if p.id == settings.provider_id), None)
    if preset is None:
        # Custom settings without a preset match: assume direct user input.
        return AIConnector(
            base_url=settings.base_url,
            api_key=settings.api_key,
            model=settings.model,
            timeout=settings.request_timeout,
            max_retries=settings.max_retries,
        )
    base_url = settings.base_url or preset.base_url
    if not settings.api_key and preset.requires_key:
        # Only complain if the user actually wants the topic-to-script flow.
        # We defer the failure to script generation to keep imports cheap.
        pass
    return AIConnector(
        base_url=base_url,
        api_key=settings.api_key,
        model=settings.model or preset.default_model,
        timeout=settings.request_timeout,
        max_retries=settings.max_retries,
    )


# --------------------------------------------------------------- pipeline


def run_render(
    settings: AppSettings,
    paths: ProjectPaths,
    *,
    on_progress: ProgressCallback | None = None,
    cancel: Callable[[], bool] | None = None,
) -> RenderResult:
    """Execute the full render pipeline and return a :class:`RenderResult`."""
    started = time.monotonic()
    notes: list[str] = []

    def emit(stage: RenderStage, message: str, **fields: object) -> None:
        if on_progress is None:
            return
        on_progress(
            RenderEvent(
                stage=stage,
                status=RenderStatus.RUNNING,
                message=message,
                fields=dict(fields),
            )
        )

    # 1. Script
    emit(RenderStage.SCRIPT, "Preparing script")
    if settings.script_file:
        script = load_script_from_file(Path(settings.script_file))
        emit(RenderStage.SCRIPT, f"Loaded script '{script.title}' with {len(script.paragraphs)} paragraphs.")
    elif settings.script_topic.strip():
        if settings.tts_backend is TTSBackend.DISABLED:
            raise ConfigError("A topic requires the script generator to run.")
        connector = build_connector(settings)
        try:
            writer = ScriptWriter(connector)
            script = writer.write(
                topic=settings.script_topic,
                target_word_count=settings.target_word_count,
                language=settings.language,
            )
        finally:
            connector.close()
        emit(
            RenderStage.SCRIPT,
            f"Generated script '{script.title}' with {script.word_count} words across {len(script.paragraphs)} paragraphs.",
        )
    else:
        raise ConfigError("Provide either a script file or a script topic.")

    if cancel is not None and cancel():
        raise SleeplensError("Render cancelled before voice rendering.")

    # 2. Voice
    emit(RenderStage.VOICE, "Rendering voice track")
    tts_engine = TTSEngine(
        backend=settings.tts_backend,
        voice=settings.tts_voice,
        rate=settings.tts_rate,
        pitch=settings.tts_pitch,
        ffmpeg_bin=paths.ffmpeg_bin,
    )
    tts_result = tts_engine.render(script.paragraphs, paths.cache_dir)
    emit(
        RenderStage.VOICE,
        f"Voice track ready ({tts_result.total_voice_duration:.1f}s, {len(tts_result.segments)} segments).",
    )

    # 3. Timing
    timing = compute_timing(
        segments=tts_result.segments,
        pause_seconds=settings.pause_between_paragraphs,
        fps=settings.video_fps,
    )
    emit(
        RenderStage.TIMING,
        f"Final runtime: {timing.human_runtime} ({timing.total_seconds:.1f}s, {timing.frame_count} frames).",
    )

    if cancel is not None and cancel():
        raise SleeplensError("Render cancelled before audio mixing.")

    # 4. Ambient
    emit(RenderStage.AMBIENT, "Selecting ambient bed")
    ambient_track = None
    if settings.ambient_mode is not AmbientMode.DISABLED:
        library = scan_ambient_library(paths.ambient_dir)
        if not library:
            notes.append(
                f"No ambient tracks found in {paths.ambient_dir}. Drop royalty-free loops into the folder and re-render."
            )
        else:
            ambient_track = pick_ambient(
                library,
                mode=settings.ambient_mode,
                script_keywords=extract_script_keywords(script.plain_text()),
            )
            if ambient_track is not None:
                emit(
                    RenderStage.AMBIENT,
                    f"Selected ambient track '{ambient_track.title}' ({ambient_track.size_mb:.1f} MB).",
                )
            else:
                notes.append("No ambient track matched; the voice plays solo.")

    # 5. Mix
    emit(RenderStage.MIX, "Mixing voice and ambient")
    mixed_path = paths.cache_dir / "mixed.wav"
    mix_bed_and_voice(
        MixSpec(
            voice_path=tts_result.track_path,
            ambient_path=ambient_track.path if ambient_track else None,
            target_duration=timing.total_seconds,
            output_path=mixed_path,
            voice_volume=settings.voice_volume,
            ambient_volume=settings.ambient_volume,
            ambient_duck_db=settings.ambient_duck_db,
            ffmpeg_bin=paths.ffmpeg_bin,
        )
    )
    emit(RenderStage.MIX, f"Mixed track ready at {mixed_path}.")

    if cancel is not None and cancel():
        raise SleeplensError("Render cancelled before video encoding.")

    # 6. Visual
    emit(RenderStage.VISUAL, "Resolving background visual")
    try:
        visual = resolve_visual(
            background_image=settings.background_image,
            background_video=settings.background_video,
            visuals_dir=paths.visuals_dir,
            target_duration=timing.total_seconds,
        )
    except SleeplensError:
        fallback_path = paths.visuals_dir / "fallback.png"
        generate_fallback(
            target_path=fallback_path,
            width=settings.video_width,
            height=settings.video_height,
            seed=settings.fallback_seed,
        )
        visual = VisualSource(path=fallback_path, kind="image", loop=False)
        notes.append("No background asset provided. Generated a dark, sleep-friendly fallback image.")
    emit(RenderStage.VISUAL, f"Background: {visual.path.name} ({visual.kind}).")

    # 7. Encode
    emit(RenderStage.ENCODE, "Encoding final video")
    stem = settings.last_output_stem or f"sleeplens-{int(started)}"
    output_path = paths.unique_output(stem)
    video_spec = VideoSpec(
        visual_path=visual.path,
        visual_kind=visual.kind,
        mixed_audio_path=mixed_path,
        output_path=output_path,
        timing=timing,
        ffmpeg_bin=paths.ffmpeg_bin,
        progress_color=settings.progress_bar_color,
        progress_height=settings.progress_bar_height,
        progress_position=settings.progress_bar_position,
        hardware_accel=settings.hardware_accel,
        render_threads=settings.render_threads,
        preset=settings.output_preset,
    )
    build(video_spec)
    emit(RenderStage.ENCODE, f"Output: {output_path}", path=str(output_path))

    elapsed = time.monotonic() - started
    log.success(
        "Render complete in {:.1f}s - {}",
        elapsed,
        output_path,
    )
    return RenderResult(
        output_path=output_path,
        script=script,
        tts=tts_result,
        timing=timing,
        visual=visual,
        duration_seconds=timing.total_seconds,
        elapsed_seconds=elapsed,
        notes=notes,
    )


__all__ = [
    "AIProvider",
    "AmbientMode",
    "OutputPreset",
    "PROVIDER_PRESETS",
    "RenderResult",
    "TTSBackend",
    "build_connector",
    "run_render",
]


# Silence the unused-import lint on Script (re-exported for type discovery).
_ = Script
