"""Test package.

Puts src/ on sys.path so that `python3 -m unittest discover`, run from the
repository root with nothing installed, can import the ledger package.
"""

import sys
from pathlib import Path

_SRC = str(Path(__file__).resolve().parent.parent / "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)
