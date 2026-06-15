"""Unit tests for the customizable progress bar avatar."""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image

# Ensure the in-tree source is importable when pytest runs from the repo root.
ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from sleep_learning_engine.video.builder import _generate_player_card  # noqa: E402


def test_generate_player_card_custom_avatar(tmp_path: Path) -> None:
    """Test that a custom avatar path is successfully processed and overlayed."""
    # Create a dummy custom avatar image (solid red square)
    custom_avatar_path = tmp_path / "custom_avatar.png"
    img = Image.new("RGBA", (100, 100), (255, 0, 0, 255))
    img.save(custom_avatar_path)

    card_path = tmp_path / "player_card.png"
    bar_path = tmp_path / "progress_bar.png"

    # Run the player card generator with custom avatar
    _generate_player_card(
        card_path=card_path,
        bar_path=bar_path,
        title_text="Test Customizable Avatar Title",
        duration_seconds=180.0,
        avatar_path=str(custom_avatar_path),
    )

    assert card_path.exists()
    assert bar_path.exists()

    # Load generated card to confirm it's valid and correct size
    card_img = Image.open(card_path)
    assert card_img.size == (750, 140)


def test_generate_player_card_fallback(tmp_path: Path) -> None:
    """Test that specifying a non-existent avatar path falls back gracefully."""
    card_path = tmp_path / "player_card.png"
    bar_path = tmp_path / "progress_bar.png"

    # Run with a non-existent file path
    _generate_player_card(
        card_path=card_path,
        bar_path=bar_path,
        title_text="Test Fallback Avatar Title",
        duration_seconds=180.0,
        avatar_path="non_existent_avatar_file.png",
    )

    assert card_path.exists()
    assert bar_path.exists()

    # Card should still render (using placeholder or autodetect fallback)
    card_img = Image.open(card_path)
    assert card_img.size == (750, 140)
