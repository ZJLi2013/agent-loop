#!/usr/bin/env python3
"""Keep an active Harness task running until independent verification passes."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from harness.core import HarnessError, completion_gate  # noqa: E402


def _workspace_root(value: str) -> Path:
    if os.name == "nt" and re.match(r"^/[A-Za-z]:/", value):
        value = value[1:]
    return Path(value)


def followup_for(payload: dict[str, object]) -> str | None:
    if payload.get("status") != "completed":
        return None
    messages: list[str] = []
    roots = payload.get("workspace_roots", [])
    if not isinstance(roots, list):
        return None
    for value in roots:
        if not isinstance(value, str):
            continue
        try:
            message = completion_gate(_workspace_root(value))
        except HarnessError as exc:
            message = f"Harness completion gate failed: {exc}"
        if message:
            messages.append(message)
    return "\n\n".join(messages) or None


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

