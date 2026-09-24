from __future__ import annotations

import hashlib
import subprocess
from pathlib import Path

from harness.storage import HARNESS_DIR

# Other agents' scratch dirs can hold locked files (WinError 1920) and never carry evidence.
FOREIGN_RUNTIME_DIRS = frozenset({".codex"})


def _foreign_runtime(parts: tuple[str, ...]) -> bool:
    return any(part in FOREIGN_RUNTIME_DIRS for part in parts[:-1])


def workspace_fingerprint(root: Path) -> str:
    root = root.resolve()
    digest = hashlib.sha256()
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        excludes = [f":(exclude){HARNESS_DIR}"] + [
            f":(exclude,glob)**/{name}/**" for name in FOREIGN_RUNTIME_DIRS
        ]
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--", ".", *excludes],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        digest.update(head)
        digest.update(diff)
        for raw_path in sorted(path for path in untracked if path):
            relative = raw_path.decode("utf-8", errors="surrogateescape")
            if relative == HARNESS_DIR or relative.startswith(f"{HARNESS_DIR}/"):
                continue
            if _foreign_runtime(tuple(relative.split("/"))):
                continue
            digest.update(raw_path)
            path = root / relative
            if path.is_file():
                with path.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        digest.update(chunk)
        return digest.hexdigest()
    except (OSError, subprocess.CalledProcessError):
        return _fallback_fingerprint(root)


def _fallback_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if relative.parts[0] in {HARNESS_DIR, ".git"} or _foreign_runtime(relative.parts):
            continue
        if not path.is_file():
            continue
        digest.update(str(relative).encode("utf-8", errors="surrogateescape"))
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()
