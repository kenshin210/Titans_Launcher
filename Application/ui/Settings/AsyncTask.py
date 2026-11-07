import subprocess
import time

from PyQt6 import sip
from PyQt6.QtCore import QThread, pyqtSignal

from Application.ui.Settings.Logger import log_warning


def run_command(command, timeout=10, input_text=None):
    try:
        return subprocess.run(
            command,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as error:
        return subprocess.CompletedProcess(command, 127, "", str(error))


def command_error(result):
    return (result.stderr or result.stdout or "unknown error").strip()


class AsyncTask(QThread):
    """Runs a callable off the UI thread and emits its return value."""

    done = pyqtSignal(object)

    def __init__(self, function, parent=None):
        super().__init__(parent)
        self._function = function

    def run(self):
        try:
            self.done.emit(self._function())
        except Exception as error:  # surfaced to the UI instead of crashing the thread
            self.done.emit(error)


# Threads are owned here, not by the widget, so closing a settings page
# while a command is running cannot destroy a live QThread.
_ACTIVE_TASKS = set()


def cleanup_all_tasks(timeout_ms=5000):
    """Wait up to the shared deadline; return False if work is still running."""
    deadline = time.monotonic() + timeout_ms / 1000
    for task in list(_ACTIVE_TASKS):
        if task.isRunning():
            remaining_ms = max(0, int((deadline - time.monotonic()) * 1000))
            if not task.wait(remaining_ms):
                log_warning("An asynchronous task is still running; launcher shutdown postponed.")
                return False
    return True


class TaskRunnerMixin:
    """Runs a callable off the UI thread and delivers the result to a callback."""

    def run_async(self, function, callback):
        task = AsyncTask(function)
        _ACTIVE_TASKS.add(task)

        def finish(result):
            if not sip.isdeleted(self):
                callback(result)

        def release():
            _ACTIVE_TASKS.discard(task)
            task.deleteLater()

        task.done.connect(finish)
        task.finished.connect(release)
        task.start()
        return task
