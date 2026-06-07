"""Entry point for `python -m sleep_learning_engine`."""

from __future__ import annotations

import sys
from pathlib import Path


def main() -> int:
    """Launch the desktop studio, or run a CLI render if --render is passed."""
    repo_root = Path(__file__).resolve().parents[2]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    from sleep_learning_engine.cli import dispatch

    return dispatch(sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
