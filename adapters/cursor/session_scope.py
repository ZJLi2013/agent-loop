from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path
from typing import Any

from adapters.core import workspace_roots
from harness.project import LEGACY_RUNTIME_DIR, RUNTIME_DIR

_SCOPES = Path(tempfile.gettempdir()) / "agent-loop-cursor-sessions"


def _scope_file(payload: dict[str, object]) -> Path | None:
    conversation_id = payload.get("conversation_id")
    if not isinstance(conversation_id, str) or not conversation_id:
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


def bind(payload: dict[str, object]) -> Path | None:
    existing = roots(payload)
    if existing:
        return existing[0]
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

    scope.parent.mkdir(parents=True, exist_ok=True)
    try:
        with scope.open("x", encoding="utf-8") as stream:
            stream.write(str(root))
    except FileExistsError:
        existing = roots(payload)
        return existing[0] if existing else None
    except OSError:
        return None
    return root


def roots(payload: dict[str, object]) -> tuple[Path, ...]:
    scope = _scope_file(payload)
    workspaces = workspace_roots(payload.get("workspace_roots"))
    if scope is None or not workspaces:
        return ()
    try:
        root = Path(scope.read_text(encoding="utf-8")).resolve()
    except OSError:
        return ()
    return (root,) if _inside(root, workspaces) else ()
