"""Launcher build and pacman package integrity checks."""
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

from Application.core.config import PROJECT_ROOT
from Application.core.packages import valid_package_name

MANIFEST_NAME = "launcher-files.sha256.json"


def build_files(root):
    files = [
        root / "launcher.py", root / "LinuxStartup.sh", root / "ArchModuleInstall.sh",
        root / "generate_launcher_manifest.py",
    ]
    files.extend((root / "Application").rglob("*.py"))
    for folder in ("Icons", "Sounds", "Styles"):
        files.extend(path for path in (root / "Assets" / folder).rglob("*") if path.is_file())
    return sorted(path.relative_to(root).as_posix() for path in files)


def make_manifest(root):
    return {name: hashlib.sha256((root / name).read_bytes()).hexdigest() for name in build_files(root)}


def check_launcher(root=PROJECT_ROOT):
    errors = []
    try:
        manifest = json.loads((root / MANIFEST_NAME).read_text(encoding="utf-8"))
        if not isinstance(manifest, dict) or not manifest:
            raise ValueError("manifest is empty or invalid")
        for name, digest in manifest.items():
            if not isinstance(name, str):
                raise ValueError("manifest contains an invalid entry")
            path = Path(name)
            if (
                path.is_absolute() or ".." in path.parts
                or not isinstance(digest, str) or len(digest) != 64
                or any(char not in "0123456789abcdef" for char in digest)
            ):
                raise ValueError("manifest contains an invalid entry")
    except (OSError, ValueError, TypeError) as error:
        manifest = {}
        errors.append(f"Checksum manifest could not be read: {error}")

    actual = set(build_files(root))
    for name in sorted(set(manifest) | actual):
        path = root / name
        if name not in manifest:
            errors.append(f"Not in build manifest: {name}")
        try:
            resolved = path.resolve(strict=True)
            if not resolved.is_relative_to(root.resolve()) or not resolved.is_file():
                raise OSError("not a regular file inside the build")
            data = resolved.read_bytes()
        except OSError as error:
            errors.append(f"Cannot read {name}: {error}")
            continue
        if name in manifest and hashlib.sha256(data).hexdigest() != manifest[name]:
            errors.append(f"Checksum mismatch: {name}")
        if name.endswith(".py"):
            try:
                compile(data, name, "exec", dont_inherit=True)
            except (SyntaxError, ValueError) as error:
                errors.append(f"Python syntax error in {name}: {error}")
    return errors, len(actual)


def check_packages(pacman, privilege_command):
    env = {**os.environ, "LC_ALL": "C"}

    def run(arguments):
        return subprocess.run(arguments, capture_output=True, text=True, errors="replace",
                              timeout=3600, check=False, env=env)

    listing = run([pacman, "-Qq"])
    if listing.returncode != 0:
        raise RuntimeError(f"Could not list installed packages: {listing.stderr.strip()}")
    packages = listing.stdout.splitlines()
    if not packages or not all(valid_package_name(name) for name in packages):
        raise RuntimeError("The installed package list is empty or invalid.")
    result = run([*privilege_command, "/usr/bin/env", "LC_ALL=C", pacman, "-Qkk", "--color", "never"])
    output = "\n".join(part for part in (result.stdout, result.stderr) if part)
    if result.returncode not in (0, 1):
        raise RuntimeError(f"Package verification failed (exit code {result.returncode}):\n{output}")
    completed = set(re.findall(
        r"^([^:\s]+): (?:\d+ total files?, \d+ altered files?|no mtree file)$",
        result.stdout, re.MULTILINE,
    ))
    if set(packages) != completed or re.search(r"^error:", output, re.MULTILINE):
        raise RuntimeError(f"Package verification was incomplete:\n{output}")
    after = run([pacman, "-Qq"])
    if after.returncode != 0 or set(after.stdout.splitlines()) != set(packages):
        raise RuntimeError("The installed package list changed during verification; run the check again.")
    return packages, result.returncode, output
