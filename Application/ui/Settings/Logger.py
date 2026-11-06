# -*- coding: utf-8 -*-
from pathlib import Path
from datetime import datetime
import threading
import sys

LOG_DIR = Path.home() / ".config" / "Titans-launcher"
LOG_FILE = LOG_DIR / "application.log"

class LauncherLogger:
    def __init__(self):
        self.lock = threading.Lock()
        self.listeners = []
        self.logs = {
            "Critical": [],
            "Error": [],
            "Warning": [],
            "Information": []
        }
        self.all_logs = []
        self.init_storage()

    def init_storage(self):
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            if LOG_FILE.exists():
                self.load_from_disk()
        except Exception as e:
            print(f"[Logger Init Error]: {e}")

    def add_listener(self, callback):
        with self.lock:
            if callback not in self.listeners:
                self.listeners.append(callback)

    def remove_listener(self, callback):
        with self.lock:
            if callback in self.listeners:
                self.listeners.remove(callback)

    def notify_listeners(self, entry):
        for cb in self.listeners:
            try:
                cb(entry)
            except Exception:
                pass

    def log(self, level, message, details=""):
        now = datetime.now()
        timestamp = now.strftime("%Y-%m-%d %H:%M:%S")
        entry = {
            "timestamp": timestamp,
            "level": level,
            "message": str(message).strip(),
            "details": str(details).strip() if details else ""
        }

        with self.lock:
            if level in self.logs:
                self.logs[level].append(entry)
                # Keep last 500 in memory per category
                if len(self.logs[level]) > 500:
                    self.logs[level].pop(0)

            self.all_logs.append(entry)
            if len(self.all_logs) > 2000:
                self.all_logs.pop(0)

            # Write to disk
            try:
                with open(LOG_FILE, "a", encoding="utf-8") as f:
                    detail_str = f" | Details: {entry['details']}" if entry['details'] else ""
                    f.write(f"[{timestamp}] [{level.upper()}] {entry['message']}{detail_str}\n")
            except Exception as e:
                print(f"[Log File Write Error]: {e}")

        # Also echo to console for CLI debugging
        print(f"[{level.upper()}] {entry['message']}")
        if entry['details']:
            print(f"   ↳ {entry['details']}")

        self.notify_listeners(entry)

    def critical(self, message, details=""):
        self.log("Critical", message, details)

    def error(self, message, details=""):
        self.log("Error", message, details)

    def warning(self, message, details=""):
        self.log("Warning", message, details)

    def info(self, message, details=""):
        self.log("Information", message, details)

    def get_logs(self, category=None):
        with self.lock:
            if category and category in self.logs:
                return list(self.logs[category])
            return list(self.all_logs)

    def clear(self, category=None):
        with self.lock:
            if category and category in self.logs:
                self.logs[category].clear()
            else:
                for k in self.logs:
                    self.logs[k].clear()
                self.all_logs.clear()
                try:
                    with open(LOG_FILE, "w", encoding="utf-8") as f:
                        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] [INFORMATION] Logs cleared by user.\n")
                except Exception:
                    pass

    def load_from_disk(self):
        if not LOG_FILE.exists():
            return
        try:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                lines = f.readlines()
                # Parse recent lines
                for line in lines[-400:]:
                    line = line.strip()
                    if not line.startswith("["):
                        continue
                    try:
                        time_part = line[1:20]
                        rest = line[22:]
                        if rest.startswith("["):
                            lvl_end = rest.find("]")
                            lvl_str = rest[1:lvl_end]
                            msg_full = rest[lvl_end+2:]

                            # Match level
                            lvl_map = {
                                "CRITICAL": "Critical",
                                "ERROR": "Error",
                                "WARNING": "Warning",
                                "INFORMATION": "Information",
                                "INFO": "Information"
                            }
                            level = lvl_map.get(lvl_str.upper(), "Information")
                            msg = msg_full
                            details = ""
                            if " | Details: " in msg_full:
                                msg, details = msg_full.split(" | Details: ", 1)

                            entry = {
                                "timestamp": time_part,
                                "level": level,
                                "message": msg,
                                "details": details
                            }
                            if level in self.logs:
                                self.logs[level].append(entry)
                            self.all_logs.append(entry)
                    except Exception:
                        continue
        except Exception as e:
            print(f"[Log Disk Read Error]: {e}")

# Global singleton
logger = LauncherLogger()

def log_critical(msg, details=""):
    logger.critical(msg, details)

def log_error(msg, details=""):
    logger.error(msg, details)

def log_warning(msg, details=""):
    logger.warning(msg, details)

def log_info(msg, details=""):
    logger.info(msg, details)

def install_excepthook():
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        import traceback
        tb = "".join(traceback.format_exception(exc_type, exc_value, exc_traceback))
        log_critical(f"Unhandled Exception: {exc_value}", details=tb)
        sys.__excepthook__(exc_type, exc_value, exc_traceback)

    sys.excepthook = handle_exception

