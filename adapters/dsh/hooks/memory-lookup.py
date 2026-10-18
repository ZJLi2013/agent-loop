#!/usr/bin/env python3
"""Translate dsh-hooks-codex SessionStart events to the agent-loop hook protocol."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from adapters.core import handle  # noqa: E402
from adapters.protocol import HookAction, HookEvent, HookRequest  # noqa: E402
from harness.project import task_file  # noqa: E402


def context_for(payload: dict[str, object]) -> str | None:
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not cwd:
        return None
    task = task_file(Path(cwd))
    if not task.is_file():
        return None
    response = handle(
        HookRequest(
            event=HookEvent.TOOL_USED,
            workspace_roots=(Path(cwd),),
            tool_input={"path": str(task)},
        )
    )
    return response.message if response.action == HookAction.CONTEXT else None


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        payload = {}
    context = context_for(payload if isinstance(payload, dict) else {})
    output = {"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    }} if context else {}
    sys.stdout.write(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
