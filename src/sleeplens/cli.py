"""Command-line entry point used by `python -m sleeplens render`."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .config import load_settings, resolve_paths, save_settings
from .core import SleeplensError, run_render
from .utils.logging import configure_logging, get_logger
from .core.state import RenderEvent

log = get_logger()


def dispatch(argv: Sequence[str]) -> int:
    """Parse argv and dispatch to the right entry point."""
    parser = _build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sleeplens",
        description="Sleep-learning video studio (CLI).",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("gui", help="Launch the desktop studio (default).").set_defaults(func=_cmd_gui)
    sub.add_parser("providers", help="List the bundled provider presets.").set_defaults(func=_cmd_providers)

    render = sub.add_parser("render", help="Run a render from the command line.")
    render.add_argument("--topic", help="Script topic (overrides settings.script_topic).")
    render.add_argument("--script", help="Path to a script file (overrides settings.script_file).")
    render.add_argument("--background-image", help="Background image path.")
    render.add_argument("--background-video", help="Background video path.")
    render.add_argument("--output-stem", help="Filename stem for the rendered MP4.")
    render.add_argument("--json", action="store_true", help="Emit a JSON summary to stdout.")
    render.set_defaults(func=_cmd_render)

    return parser


# --------------------------------------------------------------- commands


def _cmd_gui(args: argparse.Namespace) -> int:
    from .gui.main_window import launch

    paths = resolve_paths()
    paths.ensure()
    configure_logging(paths)
    launch(paths)
    return 0


def _cmd_providers(args: argparse.Namespace) -> int:
    from .config import PROVIDER_PRESETS

    for preset in PROVIDER_PRESETS:
        print(f"{preset.id}\t{preset.label}\t{preset.base_url}\t{preset.default_model}")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    paths = resolve_paths()
    paths.ensure()
    configure_logging(paths)
    settings = load_settings(paths.config_file)
    if args.topic:
        settings.script_topic = args.topic
        settings.script_file = ""
    if args.script:
        settings.script_file = args.script
        settings.script_topic = ""
    if args.background_image:
        settings.background_image = args.background_image
    if args.background_video:
        settings.background_video = args.background_video
    if args.output_stem:
        settings.last_output_stem = args.output_stem

    if not settings.script_topic and not settings.script_file:
        print(
            "No script source. Pass --topic 'your topic here' or --script path/to/file.txt",
            file=sys.stderr,
        )
        return 2

    cancelled = {"flag": False}

    def on_event(event: RenderEvent) -> None:
        if args.json:
            return
        prefix = f"[{event.stage.value:>7}]"
        print(f"{prefix} {event.message}", flush=True)

    def is_cancelled() -> bool:
        return cancelled["flag"]

    try:
        result = run_render(settings, paths, on_progress=on_event, cancel=is_cancelled)
    except SleeplensError as exc:
        log.error("Render failed: {}", exc)
        if args.json:
            print(json.dumps({"status": "failed", "error": str(exc)}))
        return 1

    if args.json:
        print(
            json.dumps(
                {
                    "status": "ok",
                    "output": str(result.output_path),
                    "duration_seconds": result.duration_seconds,
                    "elapsed_seconds": result.elapsed_seconds,
                    "paragraphs": len(result.script.paragraphs),
                    "word_count": result.script.word_count,
                    "runtime": result.timing.human_runtime,
                }
            )
        )
    return 0


__all__ = ["dispatch"]
