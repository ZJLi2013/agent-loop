#!/usr/bin/env python3
"""Translate Cursor Read events to the agent-loop hook protocol."""

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from adapters.core import handle, workspace_roots  # noqa: E402
from adapters.protocol import HookAction, HookEvent, HookRequest  # noqa: E402


def context_for(payload: dict[str, object]) -> str | None:
    response = handle(
        HookRequest(
            event=HookEvent.TOOL_USED,
            workspace_roots=workspace_roots(payload.get("workspace_roots")),
            tool_name=str(payload.get("tool_name", "")),
            tool_input=payload,
        )
    )
    return response.message if response.action == HookAction.CONTEXT else None


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    context = context_for(payload)
    sys.stdout.write(json.dumps(
        {"additional_context": context} if context else {},
        ensure_ascii=False,
    ))


if __name__ == "__main__":
    main()
