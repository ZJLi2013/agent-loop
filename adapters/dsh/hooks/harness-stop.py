#!/usr/bin/env python3
"""Translate dsh-hooks-codex Stop events to the agent-loop hook protocol."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from adapters.core import handle  # noqa: E402
from adapters.followup import claim_followup  # noqa: E402
from adapters.protocol import HookAction, HookEvent, HookRequest  # noqa: E402


def block_reason(payload: dict[str, object]) -> str | None:
    session = payload.get("session_id")
    session = session if isinstance(session, str) and session else None
    cwd = payload.get("cwd")
    try:
        response = handle(
            HookRequest(
                event=HookEvent.STOP,
                workspace_roots=(Path(cwd),) if isinstance(cwd, str) and cwd else (),
                status="completed",
                session_id=session,
            )
        )
        message = response.message if response.action == HookAction.CONTINUE else None
    except Exception as exc:
        message = (
            f"Harness stop hook failed: {exc}. Inspect the Harness state "
            "before declaring the task complete."
        )
    # stop_hook_active is always false in this bridge, so repeats are suppressed here.
    return message if message and claim_followup(session, message) else None


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    try:
        payload = json.loads(raw or "{}")
    except json.JSONDecodeError:
        payload = {}
    reason = block_reason(payload if isinstance(payload, dict) else {})
    output = {"decision": "block", "reason": reason} if reason else {}
    sys.stdout.write(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()
