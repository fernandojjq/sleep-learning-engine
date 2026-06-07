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

    cloud = sub.add_parser(
        "cloud",
        help="Open the low-RAM Colab notebook for cloud rendering.",
    )
    cloud.add_argument(
        "--repo",
        default="fernandojjq/sleeplens",
        help="GitHub repo (default: fernandojjq/sleeplens).",
    )
    cloud.add_argument(
        "--branch",
        default="main",
        help="Git branch (default: main).",
    )
    cloud.add_argument(
        "--no-browser",
        action="store_true",
        help="Print the Colab URL instead of opening the browser.",
    )
    cloud.set_defaults(func=_cmd_cloud)

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


def _cmd_cloud(args: argparse.Namespace) -> int:
    """Print (and optionally open) the Colab URL for low-RAM cloud rendering.

    The notebook is checked into the repo and runs the full sleeplens
    pipeline on a free Colab T4 GPU (NVENC + 12.7 GB RAM). It is the
    right fallback when the local machine runs out of memory during the
    final 1080p encode.
    """
    from .config import load_settings, resolve_paths

    paths = resolve_paths()
    settings = load_settings(paths.config_file)

    notebook_path = "docs/cloud/low_ram_render.ipynb"
    url = (
        f"https://colab.research.google.com/github/{args.repo}/"
        f"blob/{args.branch}/{notebook_path}"
    )

    print("Sleeplens low-RAM cloud render")
    print("=" * 60)
    print()
    print(f"Notebook:  {url}")
    print()
    print("Quick checks before you click the link:")
    script_ok = bool(settings.script_topic or settings.script_file)
    image_ok = bool(
        settings.background_image
        and Path(settings.background_image).exists()
        if settings.background_image
        else False
    )
    print(f"  Script source: {'OK' if script_ok else 'MISSING'}")
    if script_ok and settings.script_file:
        print(f"    -> {settings.script_file}")
    if script_ok and settings.script_topic:
        print(f"    -> topic: {settings.script_topic!r}")
    print(f"  Background image: {'OK' if image_ok else 'MISSING'}")
    if image_ok:
        print(f"    -> {settings.background_image}")
    print()
    print("Steps:")
    print("  1. Open the URL above in your browser.")
    print("  2. Click *Runtime -> Run all* (or press Ctrl+F9).")
    print("  3. The upload cell will ask for your script file and image.")
    print("  4. The render cell will run the full pipeline (~5 min).")
    print("  5. The download cell will save the MP4 to your machine.")
    print()
    print("See docs/CLOUD_RENDER.md for the full guide.")

    if not args.no_browser:
        import webbrowser
        try:
            webbrowser.open(url)
        except Exception as exc:  # pragma: no cover - browser launch varies
            print(f"(Could not launch browser automatically: {exc})")

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
