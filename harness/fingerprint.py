from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from harness.errors import HarnessError
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


def workspace_tree(root: Path) -> str | None:
    """Write the workspace (tracked and untracked, not ignored) as a git tree; the real index is left untouched."""
    root = root.resolve()
    # Removed after `git add`: an exclude pathspec naming an ignored path makes `git add` fail.
    runtime = [HARNESS_DIR] + [f":(glob)**/{name}/**" for name in FOREIGN_RUNTIME_DIRS]
    with tempfile.TemporaryDirectory() as temp:
        index = Path(temp) / "index"
        env = {**os.environ, "GIT_INDEX_FILE": str(index)}
        try:
            real = subprocess.run(
                ["git", "rev-parse", "--path-format=absolute", "--git-path", "index"],
                cwd=root, check=True, capture_output=True, text=True,
            ).stdout.strip()
            if Path(real).is_file():
                # Starts from the real index so unchanged files keep their stat cache and are not rehashed.
                shutil.copyfile(real, index)
            for argv in (
                ["git", "add", "-A", "--", "."],
                ["git", "rm", "-r", "-q", "--cached", "--ignore-unmatch", "--", *runtime],
            ):
                subprocess.run(argv, cwd=root, env=env, check=True, capture_output=True)
            return subprocess.run(
                ["git", "write-tree"], cwd=root, env=env, check=True, capture_output=True, text=True
            ).stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None


def workspace_diff(root: Path, tree: str) -> str | None:
    """Diff from an earlier workspace_tree to the current workspace; None when either side cannot be read."""
    current = workspace_tree(root)
    if current is None:
        return None
    try:
        return subprocess.run(
            ["git", "diff", tree, current, "--", "."],
            cwd=root.resolve(), check=True, capture_output=True, text=True, encoding="utf-8", errors="replace",
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        return None


def _file_digest(path: Path) -> str | None:
    try:
        with path.open("rb") as fh:
            return hashlib.file_digest(fh, "sha256").hexdigest()
    except OSError:
        return None


def file_digests(root: Path, paths: list[str]) -> dict[str, str | None]:
    return {relative: _file_digest(root / relative) for relative in paths}


def dirty_files(root: Path) -> dict[str, str | None]:
    """Digest each file that differs from HEAD or is untracked; empty outside a git repo."""
    root = root.resolve()
    excludes = [f":(exclude){HARNESS_DIR}"] + [
        f":(exclude,glob)**/{name}/**" for name in FOREIGN_RUNTIME_DIRS
    ]
    try:
        listed = [
            subprocess.run(
                argv, cwd=root, check=True, capture_output=True
            ).stdout.split(b"\0")
            for argv in (
                ["git", "diff", "--name-only", "-z", "--relative", "HEAD", "--", ".", *excludes],
                ["git", "ls-files", "--others", "--exclude-standard", "-z", "--", ".", *excludes],
            )
        ]
    except (OSError, subprocess.CalledProcessError):
        return {}
    paths = sorted({raw.decode("utf-8", errors="surrogateescape") for chunk in listed for raw in chunk if raw})
    return file_digests(root, paths)


def verifier_files(
    root: Path, argv: list[str], evidence_files: list[str] | None = None
) -> dict[str, str]:
    root = root.resolve()
    paths: list[Path] = []
    for arg in argv:
        try:
            paths.append((root / arg).resolve())
        except (OSError, ValueError):
            continue
    evidence: set[Path] = set()
    for declared in evidence_files or []:
        try:
            path = (root / declared).resolve()
            matches = path in paths and not path.is_dir()
        except (OSError, ValueError):
            matches = False
        if not matches:
            raise HarnessError(f"evidence file {declared!r} must match a verifier file argument")
        evidence.add(path)

    files: dict[str, str] = {}
    for path in paths:
        try:
            relative = path.relative_to(root).as_posix()
            if path in evidence or not path.is_file():
                continue
        except (OSError, ValueError):
            continue
        if digest := _file_digest(path):
            files[relative] = digest
    return files


def verifier_drift(root: Path, config: dict) -> str | None:
    root = root.resolve()
    for relative, digest in (config["verifier"].get("files") or {}).items():
        if _file_digest(root / relative) != digest:
            return relative
    return None


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
