#!/usr/bin/env python3
"""Request Goal Review when Cursor compacts an active conversation."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from harness.errors import HarnessError  # noqa: E402
from harness.plan import request_pause  # noqa: E402


def _workspace_root(value: str) -> Path:
    if os.name == "nt" and re.match(r"^/[A-Za-z]:/", value):
        value = value[1:]
    return Path(value)


def request_for(payload: dict[str, object]) -> int:
    count = 0
    roots = payload.get("workspace_roots", [])
    if not isinstance(roots, list):
        return count
    for value in roots:
        if not isinstance(value, str):
            continue
        try:
            request_pause(
                _workspace_root(value),
                reason="goal_review_due: Cursor context compacted",
                kind="goal_review",
            )
            count += 1
        except HarnessError:
            pass
    return count


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

