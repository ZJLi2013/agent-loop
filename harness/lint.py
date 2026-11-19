from __future__ import annotations

import re
import shutil
import subprocess
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit

from harness.errors import HarnessError
from harness.project import RUNTIME_DIR
from harness.storage import CONFIG_FILE, HARNESS_DIR, harness_dir, read_json

LINT_ARGV = ["agent-loop-harness", "lint", "--changed"]
ALLOW = "<!-- lint: allow -->"
LEFTOVER = re.compile(r"待验证|待确认|在跑|预计|TBD|TODO")
PRUNED_DIRS = (HARNESS_DIR, RUNTIME_DIR)

_FENCE = re.compile(r"^\s*(```|~~~)")
_CODE_SPAN = re.compile(r"(`+).*?\1")
_INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?[^)]*\)")
_REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = (getattr(exc, "stderr", None) or str(exc)).strip()
        raise HarnessError(f"git {' '.join(args)} failed: {detail}") from exc


def lint_config(root: Path) -> dict[str, Any]:
    """Settings `init --lint on` records; raises before init writes anything."""
    if not shutil.which(LINT_ARGV[0]):
        raise HarnessError(
            f"{LINT_ARGV[0]} is not on PATH; install agent-loop or init with --lint off"
        )
    try:
        base = _git(root, "rev-parse", "HEAD").strip()
    except HarnessError as exc:
        raise HarnessError(f"lint needs a git repository with a commit ({exc}); init with --lint off") from exc
    try:
        version: str | None = metadata.version("agent-loop")
    except metadata.PackageNotFoundError:
        version = None
    return {"enabled": True, "base": base, "version": version}


def _base(root: Path) -> str:
    config = harness_dir(root) / CONFIG_FILE
    if config.exists():
        return (read_json(config).get("lint") or {}).get("base") or "HEAD"
    return "HEAD"


def _markdown(listing: str) -> list[str]:
    return sorted(
        path
        for path in listing.split("\0")
        if path.lower().endswith(".md") and path.split("/", 1)[0] not in PRUNED_DIRS
    )


def _added_lines(root: Path, base: str, relative: str) -> set[int]:
    lines: set[int] = set()
    for line in _git(root, "diff", "-U0", "--relative", base, "--", relative).splitlines():
        if match := _HUNK.match(line):
            start = int(match[1])
            lines.update(range(start, start + int(match[2] or 1)))
    return lines


def _link_problem(root: Path, source: Path, target: str) -> str | None:
    if target.startswith("#"):
        return None
    parts = urlsplit(target)
    if len(parts.scheme) > 1:
        if parts.scheme in {"http", "https"} and not parts.netloc:
            return "malformed URL"
        return None
    relative = unquote(parts.path)
    if not relative:
        return None
    path = (root / relative.lstrip("/") if relative.startswith("/") else source.parent / relative).resolve()
    for name in PRUNED_DIRS:
        pruned = root / name
        if path == pruned or pruned in path.parents:
            return f"link into {name}/, which CLOSE prunes"
    return None if path.exists() else "dead link"


def _check(root: Path, relative: str, added: set[int] | None) -> list[str]:
    source = root / relative
    problems = []
    fenced = False
    for number, line in enumerate(source.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        prose = _CODE_SPAN.sub("", line)
        targets = _INLINE_LINK.findall(prose)
        if reference := _REFERENCE.match(prose):
            targets.append(reference[1])
        for target in targets:
            if reason := _link_problem(root, source, target):
                problems.append(f"{relative}:{number}: {reason}: {target}")
        if (added is None or number in added) and ALLOW not in line:
            if word := LEFTOVER.search(prose):
                problems.append(
                    f"{relative}:{number}: leftover {word[0]!r}; finish the line or mark it {ALLOW}"
                )
    return problems


def lint_changed(root: Path) -> list[str]:
    """Problems in the markdown changed since this task's init (HEAD without a task)."""
    root = root.resolve()
    base = _base(root)
    tracked = _markdown(_git(root, "diff", "--name-only", "-z", "--relative", "--diff-filter=d", base, "--"))
    untracked = _markdown(_git(root, "ls-files", "--others", "--exclude-standard", "-z"))
    problems = [f"{relative}: not tracked by git" for relative in untracked]
    for relative in tracked:
        problems += _check(root, relative, _added_lines(root, base, relative))
    for relative in untracked:
        problems += _check(root, relative, None)
    return problems
