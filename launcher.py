"""Compatibility entry point for the Titans Launcher application."""

import sys
from pathlib import Path

# Keep compiled bytecode out of the source folders.
sys.pycache_prefix = str(Path(__file__).resolve().parent / "Garbage" / "__pycache__")

if __name__ == "__main__":
    from Application.startup import start_startup_screen

    startup_screen = start_startup_screen()
    try:
        from Application.launcher import *
        main(startup_screen)
    finally:
        if startup_screen is not None:
            startup_screen.close()
else:
    from Application.launcher import *
