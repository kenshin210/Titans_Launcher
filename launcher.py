"""Compatibility entry point for the Titans Launcher application."""

import sys
from pathlib import Path

# Keep compiled bytecode out of the source folders.
sys.pycache_prefix = str(Path(__file__).resolve().parent / "Garbage" / "__pycache__")

from Application.launcher import *


if __name__ == "__main__":
    main()
