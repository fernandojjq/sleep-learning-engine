"""One-shot launcher used by the README quickstart.

Usage:
    python run.py                # launch the GUI
    python run.py providers      # list bundled provider presets
    python run.py render --prompt "a calm lesson on breathing"
"""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure the in-tree source is importable without an editable install.
ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

from sleeplens.cli import dispatch

if __name__ == "__main__":
    raise SystemExit(dispatch(sys.argv[1:]))
