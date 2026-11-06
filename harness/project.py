from __future__ import annotations

import re
from pathlib import Path

from harness.errors import HarnessError

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


def _git_common_dir(root: Path) -> Path | None:
    # Read the files instead of running git: the worktree may have been created on another host.
    dot_git = root / ".git"
    if dot_git.is_dir():
        return dot_git
    if not dot_git.is_file():
        return None
    try:
        text = dot_git.read_text(encoding="utf-8").strip()
        if not text.startswith("gitdir:"):
            raise OSError(f"no gitdir line in {text[:80]!r}")
        gitdir = root / text.removeprefix("gitdir:").strip()
        commondir = gitdir / "commondir"
        common = gitdir / commondir.read_text(encoding="utf-8").strip() if commondir.is_file() else gitdir
        if not common.is_dir():
            raise OSError(f"{common} is not a directory")
    except OSError as error:
        raise HarnessError(f"cannot locate the git directory from {dot_git}: {error}") from error
    return common.resolve()


def worktree_memory(root: Path) -> Path:
    root = root.resolve()
    current = root / RUNTIME_DIR / "memory"
    legacy = root / LEGACY_RUNTIME_DIR / "memory"
    if current.exists() or not legacy.exists():
        return current
    return legacy


def memory_dir(root: Path) -> Path:
    common = _git_common_dir(root.resolve())
    return common / "agent-loop" / "memory" if common else worktree_memory(root)
