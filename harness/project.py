from __future__ import annotations

import re
from pathlib import Path

RUNTIME_DIR = ".agent-loop"
LEGACY_RUNTIME_DIR = ".cursor"
PROMPT_DIR = Path(__file__).with_name("prompts")
PLACEHOLDER = re.compile(r"\{([a-z_]+)\}")


def render_prompt(name: str, **values: object) -> str:
    text = (PROMPT_DIR / name).read_text(encoding="utf-8")
    return PLACEHOLDER.sub(lambda match: str(values[match.group(1)]), text)


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


def review_checklist(root: Path) -> Path | None:
    path = runtime_dir(root) / "review-checklist.md"
    return path if path.is_file() else None


def _main_worktree(root: Path) -> Path:
    # A linked worktree's .git file names its gitdir, whose commondir leads to the main worktree's .git.
    try:
        gitdir = (root / ".git").read_text(encoding="utf-8").strip().removeprefix("gitdir:").strip()
        common = ((root / gitdir) / (root / gitdir / "commondir").read_text(encoding="utf-8").strip()).resolve()
    except OSError:
        return root
    return common.parent if common.name == ".git" else root


def memory_dir(root: Path) -> Path:
    root = _main_worktree(root.resolve())
    current = root / RUNTIME_DIR / "memory"
    legacy = root / LEGACY_RUNTIME_DIR / "memory"
    if current.exists() or not legacy.exists():
        return current
    return legacy
