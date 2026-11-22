"""Start and dismiss the separate loading screen process."""
import os
import select
import subprocess
import sys
from pathlib import Path


class StartupScreenProcess:
    def __init__(self, process):
        self.process = process

    def close(self):
        if self.process is None:
            return
        process, self.process = self.process, None
        if process.stdin:
            process.stdin.close()
        try:
            process.wait(timeout=2)
        except subprocess.TimeoutExpired:
            print("Startup screen did not close; stopping it.", file=sys.stderr)
            try:
                process.terminate()
            except ProcessLookupError:
                pass
            try:
                process.wait(timeout=2)
            except subprocess.TimeoutExpired:
                try:
                    process.kill()
                except ProcessLookupError:
                    pass
                process.wait()
        if process.stdout:
            process.stdout.close()


def start_startup_screen():
    root = Path(__file__).resolve().parent.parent
    try:
        process = subprocess.Popen(
            [sys.executable, "-m", "Application.ui.startup_screen"],
            cwd=root,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
        )
    except OSError as error:
        print(f"Could not start the loading screen: {error}", file=sys.stderr)
        return None

    screen = StartupScreenProcess(process)
    try:
        ready, _, _ = select.select([process.stdout], [], [], 8)
        if not ready or os.read(process.stdout.fileno(), 6) != b"READY\n":
            print("The loading screen did not become ready; continuing without it.", file=sys.stderr)
            screen.close()
            return None
    except OSError as error:
        print(f"Could not initialize the loading screen: {error}", file=sys.stderr)
        screen.close()
        return None
    return screen
