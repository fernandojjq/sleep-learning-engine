"""Visual assets: user-provided backgrounds and procedural fallback."""

from __future__ import annotations

import random
import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from ..core import AssetNotFoundError, ConfigError, DependencyMissingError
from ..utils.logging import get_logger

log = get_logger()

IMAGE_SUFFIXES: frozenset[str] = frozenset({".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"})
VIDEO_SUFFIXES: frozenset[str] = frozenset({".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"})


@dataclass(frozen=True)
class VisualSource:
    """The background that will play behind the voice."""

    path: Path
    kind: str  # "image" or "video".
    loop: bool  # True when the source is a short clip that must loop.
    duration_hint: float = 0.0  # For videos, the intrinsic duration.

    @property
    def suffix(self) -> str:
        return self.path.suffix.lower()


def resolve_visual(
    *,
    background_image: str,
    background_video: str,
    visuals_dir: Path,
    target_duration: float,
) -> VisualSource:
    """Pick the background asset the renderer will use.

    Priority: explicit video > explicit image > first file in ``visuals_dir``.
    If nothing is provided, the caller must call :func:`generate_fallback` to
    create a synthetic dark image.
    """
    if background_video:
        path = Path(background_video).expanduser().resolve()
        if not path.exists():
            raise AssetNotFoundError(f"Background video not found: {path}")
        if path.suffix.lower() not in VIDEO_SUFFIXES:
            raise ConfigError(f"Unsupported video format: {path.suffix}")
        return VisualSource(path=path, kind="video", loop=False)

    if background_image:
        path = Path(background_image).expanduser().resolve()
        if not path.exists():
            raise AssetNotFoundError(f"Background image not found: {path}")
        if path.suffix.lower() not in IMAGE_SUFFIXES:
            raise ConfigError(f"Unsupported image format: {path.suffix}")
        return VisualSource(path=path, kind="image", loop=False)

    # Look inside the bundled visuals directory.
    if visuals_dir.exists():
        for entry in sorted(visuals_dir.iterdir()):
            if not entry.is_file():
                continue
            if entry.suffix.lower() in IMAGE_SUFFIXES:
                return VisualSource(path=entry, kind="image", loop=False)
            if entry.suffix.lower() in VIDEO_SUFFIXES:
                return VisualSource(path=entry, kind="video", loop=True, duration_hint=0.0)

    raise AssetNotFoundError(
        "No visual asset is available. Provide a background image/video or "
        "let the studio generate a synthetic dark backdrop."
    )


# ------------------------------------------------------------- fallback


def generate_fallback(
    *,
    target_path: Path,
    width: int = 1280,
    height: int = 720,
    seed: int = 20251123,
    palette: str = "midnight",
) -> Path:
    """Render a dark-themed, sleep-friendly backdrop to ``target_path``.

    The image is procedural and deterministic given a seed, so renders are
    reproducible. No network is touched, no API key is required.
    """
    try:
        from PIL import Image, ImageDraw, ImageFilter, ImageFont
    except ImportError as exc:
        raise DependencyMissingError("Pillow is required to generate fallback visuals.") from exc

    target_path.parent.mkdir(parents=True, exist_ok=True)
    rng = random.Random(seed)
    palette_rgb = _palette(palette)
    base = palette_rgb["base"]
    accent = palette_rgb["accent"]

    img = Image.new("RGB", (width, height), base)
    draw = ImageDraw.Draw(img)

    # Soft horizontal gradient from top to bottom.
    for y in range(height):
        t = y / max(1, height - 1)
        r = int(base[0] * (1 - t) + accent[0] * t * 0.18)
        g = int(base[1] * (1 - t) + accent[1] * t * 0.18)
        b = int(base[2] * (1 - t) + accent[2] * t * 0.22)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    # Faint stars (deterministic) for a sense of depth.
    star_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    star_draw = ImageDraw.Draw(star_layer)
    for _ in range(int(width * height / 4500)):
        x = rng.randint(0, width - 1)
        y = rng.randint(0, height - 1)
        radius = rng.choice([1, 1, 1, 2])
        brightness = rng.randint(80, 200)
        alpha = rng.randint(60, 180)
        star_draw.ellipse(
            (x - radius, y - radius, x + radius, y + radius),
            fill=(brightness, brightness, brightness, alpha),
        )
    star_layer = star_layer.filter(ImageFilter.GaussianBlur(radius=0.6))
    img = Image.alpha_composite(img.convert("RGBA"), star_layer).convert("RGB")

    # Subtle horizon glow band.
    band = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    band_draw = ImageDraw.Draw(band)
    band_y = int(height * 0.62)
    for offset in range(0, 80, 2):
        alpha = int(40 * (1 - offset / 80))
        band_draw.ellipse(
            (-120, band_y - offset, width + 120, band_y + offset + 30),
            fill=(accent[0], accent[1], accent[2], alpha),
        )
    band = band.filter(ImageFilter.GaussianBlur(radius=14))
    img = Image.alpha_composite(img.convert("RGBA"), band).convert("RGB")

    # A whisper of a quote-like line in the centre (kept small + low contrast).
    try:
        font = ImageFont.truetype("arial.ttf", size=18)
    except OSError:
        font = ImageFont.load_default()
    text = "breathe in . breathe out"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_width = bbox[2] - bbox[0]
    text_height = bbox[3] - bbox[1]
    draw.text(
        ((width - text_width) / 2, height * 0.85 - text_height / 2),
        text,
        font=font,
        fill=(170, 175, 190),
    )

    img.save(target_path, format="PNG", optimize=True)
    log.info("Generated fallback visual at {}", target_path)
    return target_path


def _palette(name: str) -> dict[str, tuple[int, int, int]]:
    palettes = {
        "midnight": {"base": (10, 12, 24), "accent": (60, 80, 130)},
        "aurora": {"base": (8, 18, 26), "accent": (90, 180, 170)},
        "ember": {"base": (16, 10, 14), "accent": (170, 80, 60)},
        "violet": {"base": (14, 8, 24), "accent": (130, 90, 180)},
    }
    return palettes.get(name, palettes["midnight"])


# ----------------------------------------------------- public exports


__all__ = [
    "IMAGE_SUFFIXES",
    "VIDEO_SUFFIXES",
    "VisualSource",
    "generate_fallback",
    "resolve_visual",
]


# Silence the unused-import lint on shutil (kept for future move operations).
_ = shutil
