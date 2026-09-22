#!/usr/bin/env python3
"""Translate Cursor compact events to the agent-loop hook protocol."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from adapters.core import request_goal_review, workspace_roots  # noqa: E402


def request_for(payload: dict[str, object]) -> int:
    return request_goal_review(
        workspace_roots(payload.get("workspace_roots"))
    )


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    try:
        payload = json.loads(raw or "{}")
        if isinstance(payload, dict):
            request_for(payload)
    except json.JSONDecodeError:
        pass
    sys.stdout.write("{}")


if __name__ == "__main__":
    main()

