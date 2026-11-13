import hashlib
import json
import os
import shutil
import stat
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path, PurePosixPath
from urllib.request import Request, urlopen

from PyQt6.QtCore import QObject, QTimer, pyqtSignal

from Application.core.config import PROJECT_ROOT
from Application.core.file_check import (
    MANIFEST_NAME,
    build_files,
    check_launcher,
    is_build_file_name,
    make_manifest,
)
from Application.ui.Settings.AsyncTask import TaskRunnerMixin
from Application.ui.Settings.Logger import log_error, log_warning


GITHUB_REPOSITORY = "kenshin210/Titans_Launcher"
GITHUB_REPOSITORY_URL = f"https://github.com/{GITHUB_REPOSITORY}.git"
GITHUB_API_URL = f"https://api.github.com/repos/{GITHUB_REPOSITORY}"
UPDATE_CHANNELS = ("Stable", "Beta")
DEFAULT_UPDATE_CHANNEL = "Stable"
UPDATE_INTERVAL_MS = 6 * 60 * 60 * 1000
MAX_API_RESPONSE_BYTES = 5_000_000
MAX_ARCHIVE_BYTES = 100_000_000
MAX_ARCHIVE_FILE_BYTES = 50_000_000


def _read_url(url, accept, max_bytes):
    request = Request(
        url,
        headers={
            "Accept": accept,
            "User-Agent": "TitansLauncher",
        },
    )
    with urlopen(request, timeout=30) as response:
        content = response.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError(f"GitHub response exceeds the {max_bytes}-byte limit.")
    return content


def _read_json(url):
    content = _read_url(
        url,
        "application/vnd.github+json",
        MAX_API_RESPONSE_BYTES,
    )
    result = json.loads(content)
    if not isinstance(result, dict):
        raise ValueError("GitHub returned an unexpected response.")
    return result


def fetch_branch_tree(branch):
    if branch not in UPDATE_CHANNELS:
        raise ValueError(f"Unsupported launcher update channel: {branch}")
    commit = _read_json(f"{GITHUB_API_URL}/commits/{branch}")
    commit_sha = commit.get("sha")
    tree_sha = commit.get("commit", {}).get("tree", {}).get("sha")
    if not isinstance(commit_sha, str) or not isinstance(tree_sha, str):
        raise ValueError(f"GitHub did not return a valid {branch} branch commit.")

    tree = _read_json(f"{GITHUB_API_URL}/git/trees/{tree_sha}?recursive=1")
    if tree.get("truncated"):
        raise ValueError("GitHub's repository tree response was truncated.")
    entries = tree.get("tree")
    if not isinstance(entries, list):
        raise ValueError("GitHub did not return a valid repository tree.")

    files = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        path = entry.get("path")
        if not is_build_file_name(path):
            continue
        if entry.get("type") != "blob" or entry.get("mode") not in {"100644", "100755"}:
            raise ValueError(f"Unsupported launcher file type in GitHub tree: {path}")
        file_sha = entry.get("sha")
        if not isinstance(file_sha, str):
            raise ValueError(f"GitHub did not return a valid file hash for {path}.")
        files[path] = file_sha
    if not files:
        raise ValueError(f"GitHub's {branch} branch contains no launcher build files.")

    message = commit.get("commit", {}).get("message", "")
    return {
        "sha": commit_sha,
        "message": message.splitlines()[0] if isinstance(message, str) else "",
        "files": files,
    }


def _git_blob_sha(content):
    header = f"blob {len(content)}\0".encode("ascii")
    return hashlib.sha1(header + content).hexdigest()


def _safe_build_path(name):
    if name == MANIFEST_NAME:
        return PurePosixPath(name)
    if not is_build_file_name(name):
        raise ValueError(f"Unsafe or unsupported launcher path: {name}")
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "\\" in name:
        raise ValueError(f"Unsafe launcher path: {name}")
    return path


class GitHubUpdateService(QObject, TaskRunnerMixin):
    changed = pyqtSignal()

    def __init__(self, owner=None, root=PROJECT_ROOT, auto_start=True):
        super().__init__(owner if isinstance(owner, QObject) else None)
        self.owner = owner
        self.root = Path(root).resolve()
        self.busy = False
        self.installing = False
        self.available = False
        self.status = "GitHub update check has not run yet."
        self.remote_info = None
        self._timer = QTimer(self)
        self._timer.setInterval(UPDATE_INTERVAL_MS)
        self._timer.timeout.connect(self.check)
        if auto_start:
            self._timer.start()
            QTimer.singleShot(15_000, self.check)

    @property
    def branch(self):
        config = getattr(self.owner, "config", None)
        branch = (
            config.get("_launcher_update_branch", DEFAULT_UPDATE_CHANNEL)
            if isinstance(config, dict)
            else DEFAULT_UPDATE_CHANNEL
        )
        if branch not in UPDATE_CHANNELS:
            log_warning(f"Invalid launcher update channel {branch!r}; using Stable.")
            return DEFAULT_UPDATE_CHANNEL
        return branch

    def set_branch(self, branch):
        if branch not in UPDATE_CHANNELS:
            raise ValueError(f"Unsupported launcher update channel: {branch}")
        if self.busy:
            raise RuntimeError("Wait for the current launcher update task to finish.")
        config = getattr(self.owner, "config", None)
        if not isinstance(config, dict):
            raise RuntimeError("Launcher update settings are unavailable.")
        if config.get("_launcher_update_branch", DEFAULT_UPDATE_CHANNEL) == branch:
            return

        config["_launcher_update_branch"] = branch
        save_config = getattr(self.owner, "save_config_file", None)
        if callable(save_config):
            save_config()
        self.available = False
        self.remote_info = None
        self.status = f"Checking the {branch} update channel..."
        self.changed.emit()
        self.check()

    def check(self):
        if self.busy:
            return
        branch = self.branch
        self.busy = True
        self.status = f"Checking GitHub's {branch} branch for launcher updates..."
        self.changed.emit()
        self.run_async(lambda: self._check_remote(branch), self._complete_check)

    def _check_remote(self, branch):
        remote = fetch_branch_tree(branch)
        local_files = {}
        for name in build_files(self.root):
            local_files[name] = _git_blob_sha((self.root / name).read_bytes())
        changed_files = sorted(
            name
            for name in set(remote["files"]) | set(local_files)
            if remote["files"].get(name) != local_files.get(name)
        )
        return {**remote, "branch": branch, "changed_files": changed_files}

    def _complete_check(self, result):
        self.busy = False
        if isinstance(result, Exception):
            self.available = False
            self.remote_info = None
            self.status = f"Could not check GitHub for launcher updates: {result}"
            log_warning(self.status)
        else:
            self.remote_info = result
            self.available = bool(result["changed_files"])
            if self.available:
                self.status = (
                    f"Launcher update available on GitHub {result['branch']} "
                    f"({result['sha'][:7]}; {len(result['changed_files'])} changed files)."
                )
                self._notify_available(result["sha"], result["branch"])
            else:
                self.status = (
                    f"The launcher is up to date with GitHub {result['branch']}."
                )
        self.changed.emit()

    def _notify_available(self, commit_sha, branch):
        config = getattr(self.owner, "config", None)
        notified = config.get("_github_launcher_update_notified", {}) if isinstance(config, dict) else {}
        previous_sha = notified.get(branch) if isinstance(notified, dict) else None
        if previous_sha == commit_sha:
            return

        if isinstance(config, dict):
            config["_github_launcher_update_notified"] = {
                **(notified if isinstance(notified, dict) else {}),
                branch: commit_sha,
            }
            save_config = getattr(self.owner, "save_config_file", None)
            if callable(save_config):
                save_config()

        notify_send = shutil.which("notify-send")
        if notify_send is None:
            log_warning("Launcher update is available, but notify-send is not installed.")
            return
        try:
            subprocess.Popen(
                [
                    notify_send,
                    "Titans Launcher update available",
                    f"GitHub {branch} has a new launcher update ({commit_sha[:7]}).",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
        except OSError as error:
            log_warning(f"Could not show the launcher update notification: {error}")

    def install(self):
        if self.busy or not self.available or self.remote_info is None:
            return
        self.busy = True
        self.installing = True
        self.status = "Installing the confirmed GitHub launcher update..."
        self.changed.emit()
        remote_info = self.remote_info
        self.run_async(
            lambda: self._install_remote(remote_info),
            self._complete_install,
        )

    def _complete_install(self, result):
        self.busy = False
        self.installing = False
        if isinstance(result, Exception):
            self.status = f"Launcher update failed: {result}"
            log_error(self.status)
        else:
            self.available = False
            self.remote_info = None
            self.status = (
                f"Launcher update installed from GitHub {result['branch']} "
                f"({result['sha'][:7]}). "
                "Restart Titans Launcher to apply it."
            )
        self.changed.emit()

    def _install_remote(self, remote_info):
        if not self.root.is_dir():
            raise RuntimeError(f"Launcher installation directory does not exist: {self.root}")
        if (self.root / ".git").exists():
            return self._update_git_checkout(remote_info)
        return self._update_archive(remote_info)

    def _run_git(self, *args):
        result = subprocess.run(
            ["git", "-C", str(self.root), *args],
            capture_output=True,
            text=True,
            timeout=180,
            check=False,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if result.returncode:
            message = result.stderr.strip() or result.stdout.strip()
            raise RuntimeError(message or "Git command failed.")
        return result.stdout.strip()

    def _update_git_checkout(self, remote_info):
        if self._run_git("status", "--porcelain", "--untracked-files=normal"):
            raise RuntimeError(
                "This Git checkout has local changes. Preserve them and update it manually."
            )

        branch = remote_info["branch"]
        self._run_git("fetch", "--no-tags", GITHUB_REPOSITORY_URL, branch)
        if self._run_git("branch", "--list", branch):
            self._run_git("switch", branch)
            self._run_git("merge", "--ff-only", "FETCH_HEAD")
        else:
            self._run_git("switch", "--create", branch, "FETCH_HEAD")
        manifest_path = self.root / MANIFEST_NAME
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.root,
            prefix=".launcher-manifest-",
            suffix=".tmp",
            delete=False,
        ) as manifest_file:
            temporary_manifest = Path(manifest_file.name)
            json.dump(make_manifest(self.root), manifest_file, indent=2, sort_keys=True)
            manifest_file.write("\n")
        try:
            os.replace(temporary_manifest, manifest_path)
        finally:
            temporary_manifest.unlink(missing_ok=True)
        errors, _ = check_launcher(self.root)
        if errors:
            raise RuntimeError(
                "The GitHub update completed, but launcher verification failed: "
                + "; ".join(errors[:5])
            )
        return {
            "sha": self._run_git("rev-parse", "HEAD"),
            "branch": branch,
            "mode": "git",
        }

    def _update_archive(self, remote_info):
        errors, _ = check_launcher(self.root)
        if errors:
            raise RuntimeError(
                "The installed launcher has local file-check errors. Resolve them before "
                "updating: "
                + "; ".join(errors[:5])
            )

        archive_data = _read_url(
            f"https://codeload.github.com/{GITHUB_REPOSITORY}/zip/{remote_info['sha']}",
            "application/zip",
            MAX_ARCHIVE_BYTES,
        )
        remote_files = remote_info["files"]
        staged_data = {}

        with zipfile.ZipFile(BytesIO(archive_data)) as archive:
            names = archive.namelist()
            top_level = {
                PurePosixPath(name).parts[0]
                for name in names
                if PurePosixPath(name).parts
            }
            if len(top_level) != 1:
                raise ValueError("GitHub archive has an unexpected directory structure.")
            prefix = next(iter(top_level)) + "/"
            total_size = 0
            for name, expected_sha in remote_files.items():
                safe_path = _safe_build_path(name)
                archive_name = prefix + safe_path.as_posix()
                try:
                    info = archive.getinfo(archive_name)
                except KeyError as error:
                    raise ValueError(f"GitHub archive is missing {name}.") from error
                mode = info.external_attr >> 16
                if stat.S_ISLNK(mode) or info.is_dir():
                    raise ValueError(f"GitHub archive contains an unsafe entry for {name}.")
                if info.file_size > MAX_ARCHIVE_FILE_BYTES:
                    raise ValueError(f"GitHub archive file is too large: {name}")
                total_size += info.file_size
                if total_size > MAX_ARCHIVE_BYTES:
                    raise ValueError("GitHub archive contains too much launcher data.")
                content = archive.read(info)
                if _git_blob_sha(content) != expected_sha:
                    raise ValueError(f"GitHub archive hash mismatch for {name}.")
                staged_data[name] = content

        manifest = {
            name: hashlib.sha256(content).hexdigest()
            for name, content in staged_data.items()
        }
        manifest_content = (
            json.dumps(manifest, indent=2, sort_keys=True) + "\n"
        ).encode("utf-8")
        with tempfile.TemporaryDirectory(
            prefix=".titans-update-",
            dir=self.root,
        ) as temporary_directory:
            temporary_root = Path(temporary_directory)
            for name, content in staged_data.items():
                stage_path = temporary_root / "stage" / name
                stage_path.parent.mkdir(parents=True, exist_ok=True)
                stage_path.write_bytes(content)
            staged_manifest = temporary_root / "stage" / MANIFEST_NAME
            staged_manifest.write_bytes(manifest_content)

            old_manifest = json.loads((self.root / MANIFEST_NAME).read_text(encoding="utf-8"))
            if not isinstance(old_manifest, dict):
                raise ValueError("The installed launcher manifest is invalid.")
            old_names = set(old_manifest)
            for name in old_names:
                _safe_build_path(name)
            target_names = sorted(
                set(remote_files) | (old_names - set(remote_files)) | {MANIFEST_NAME}
            )
            original_exists = {}
            for name in target_names:
                target = self.root / _safe_build_path(name)
                if target.is_symlink():
                    raise ValueError(f"Refusing to replace a symlink: {name}")
                original_exists[name] = target.exists()
                if target.exists():
                    if not target.is_file():
                        raise ValueError(f"Refusing to replace a non-file: {name}")
                    backup = temporary_root / "backup" / name
                    backup.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copy2(target, backup)

            try:
                for name in sorted(remote_files):
                    target = self.root / _safe_build_path(name)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    os.replace(temporary_root / "stage" / name, target)
                os.replace(staged_manifest, self.root / MANIFEST_NAME)
                for name in old_names - set(remote_files):
                    (self.root / _safe_build_path(name)).unlink(missing_ok=True)
                errors, _ = check_launcher(self.root)
                if errors:
                    raise RuntimeError(
                        "Updated launcher failed verification: " + "; ".join(errors[:5])
                    )
            except Exception as error:
                rollback_errors = []
                for name in reversed(target_names):
                    target = self.root / _safe_build_path(name)
                    try:
                        if original_exists[name]:
                            backup = temporary_root / "backup" / name
                            if backup.exists():
                                os.replace(backup, target)
                        elif target.exists():
                            target.unlink()
                    except OSError as rollback_error:
                        rollback_errors.append(f"{name}: {rollback_error}")
                if rollback_errors:
                    raise RuntimeError(
                        f"{error}; rollback was incomplete: {'; '.join(rollback_errors)}"
                    ) from error
                raise

        return {
            "sha": remote_info["sha"],
            "branch": remote_info["branch"],
            "mode": "archive",
        }
