#!/usr/bin/env python3
"""Translate Cursor compact events to the agent-loop hook protocol."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from adapters.core import request_goal_review  # noqa: E402
from adapters.cursor.session_scope import roots, session_id  # noqa: E402

LARGE_CONTEXT_WINDOW = 1_000_000


def request_for(payload: dict[str, object]) -> int:
    return request_goal_review(roots(payload), session_id(payload))


def output_for(raw: str) -> str:
    try:
        payload = json.loads(raw or "{}")
        if isinstance(payload, dict):
            paused = request_for(payload)
            if paused:
                message = (
                    "Context compacted. agent-loop paused the Harness runner "
                    "for Goal Review before the next action."
                )
                window = payload.get("context_window_size")
                if isinstance(window, int) and window < LARGE_CONTEXT_WINDOW:
                    message += (
                        f" This session has a {window:,}-token context window; "
                        "a larger-context model can reduce repeated compactions."
                    )
                return json.dumps({"user_message": message})
    except json.JSONDecodeError:
        pass
    return "{}"


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    sys.stdout.write(output_for(raw))


if __name__ == "__main__":
    main()

