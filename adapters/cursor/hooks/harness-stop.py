#!/usr/bin/env python3
"""Translate Cursor stop events to the agent-loop hook protocol."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from adapters.core import handle, workspace_roots  # noqa: E402
from adapters.protocol import HookAction, HookEvent, HookRequest  # noqa: E402


def followup_for(payload: dict[str, object]) -> str | None:
    response = handle(
        HookRequest(
            event=HookEvent.STOP,
            workspace_roots=workspace_roots(payload.get("workspace_roots")),
            status=str(payload.get("status", "")),
        )
    )
    return response.message if response.action == HookAction.CONTINUE else None


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    try:
        payload = json.loads(raw or "{}")
        if not isinstance(payload, dict):
            payload = {}
        followup = followup_for(payload)
        output = {"followup_message": followup} if followup else {}
    except Exception as exc:
        output = {
            "followup_message": (
                f"Harness stop hook failed: {exc}. Inspect the Harness state "
                "before declaring the task complete."
            )
        }
    sys.stdout.write(json.dumps(output, ensure_ascii=False))


if __name__ == "__main__":
    main()

