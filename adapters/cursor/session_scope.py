from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

from adapters.core import workspace_roots
from harness.project import LEGACY_RUNTIME_DIR, RUNTIME_DIR

_SCOPES = Path(tempfile.gettempdir()) / "agent-loop-cursor-sessions"


def session_id(payload: dict[str, object]) -> str | None:
    value = payload.get("conversation_id")
    return value if isinstance(value, str) and value else None


def _scope_file(payload: dict[str, object]) -> Path | None:
    conversation_id = session_id(payload)
    if conversation_id is None:
        return None
    name = hashlib.sha256(conversation_id.encode()).hexdigest()
    return _SCOPES / name


def _task_path(payload: Any) -> Path | None:
    stack = [payload]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, str):
            path = Path(value)
            if (
                path.name.lower() == "task.md"
                and path.parent.name in {RUNTIME_DIR, LEGACY_RUNTIME_DIR}
            ):
                return path
    return None


def _inside(root: Path, workspaces: tuple[Path, ...]) -> bool:
    return any(
        root == workspace or root.is_relative_to(workspace)
        for workspace in (path.resolve() for path in workspaces)
    )


def _scope_lines(scope: Path) -> list[str]:
    try:
        text = scope.read_text(encoding="utf-8")
    except OSError:
        return []
    return [line.strip() for line in text.splitlines() if line.strip()]


def bind(payload: dict[str, object]) -> Path | None:
    scope = _scope_file(payload)
    task = _task_path(payload.get("tool_input"))
    workspaces = workspace_roots(payload.get("workspace_roots"))
    if scope is None or task is None or not workspaces:
        return None
    candidates = (
        (task,)
        if task.is_absolute()
        else tuple(workspace / task for workspace in workspaces)
    )
    root = next(
        (
            candidate.parent.parent.resolve()
            for candidate in candidates
            if candidate.is_file()
            and _inside(candidate.parent.parent.resolve(), workspaces)
        ),
        None,
    )
    if root is None:
        return None

    lines = _scope_lines(scope)
    if str(root) in lines:
        return root
    try:
        scope.parent.mkdir(parents=True, exist_ok=True)
        scope.write_text("\n".join([*lines, str(root)]) + "\n", encoding="utf-8")
    except OSError:
        return None
    return root


def roots(payload: dict[str, object]) -> tuple[Path, ...]:
    scope = _scope_file(payload)
    workspaces = workspace_roots(payload.get("workspace_roots"))
    if scope is None or not workspaces:
        return ()
    found: list[Path] = []
    for line in _scope_lines(scope):
        root = Path(line).resolve()
        if _inside(root, workspaces) and root not in found:
            found.append(root)
    return tuple(found)
