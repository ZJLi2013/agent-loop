from __future__ import annotations

from pathlib import Path

RUNTIME_DIR = ".agent-loop"
LEGACY_RUNTIME_DIR = ".cursor"


def runtime_dir(root: Path) -> Path:
    root = root.resolve()
    current = root / RUNTIME_DIR
    legacy = root / LEGACY_RUNTIME_DIR
    legacy_runtime_exists = any(
        (legacy / name).exists()
        for name in ("task.md", "progress.md", "memory")
    )
    if current.exists() or not legacy_runtime_exists:
        return current
    return legacy


def task_file(root: Path) -> Path:
    root = root.resolve()
    current = root / RUNTIME_DIR / "task.md"
    legacy = root / LEGACY_RUNTIME_DIR / "task.md"
    if current.exists() or not legacy.exists():
        return current
    return legacy


def memory_dir(root: Path) -> Path:
    root = root.resolve()
    current = root / RUNTIME_DIR / "memory"
    legacy = root / LEGACY_RUNTIME_DIR / "memory"
    if current.exists() or not legacy.exists():
        return current
    return legacy
