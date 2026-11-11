#!/usr/bin/env python3
"""Translate Cursor compact events to the agent-loop hook protocol."""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from harness.compaction import LARGE_CONTEXT_WINDOW, record_compaction  # noqa: E402
from adapters.cursor.session_scope import session_id  # noqa: E402


def output_for(raw: str) -> str:
    try:
        payload = json.loads(raw or "{}")
        if isinstance(payload, dict):
            window = payload.get("context_window_size")
            if not isinstance(window, int):
                window = None
            record_compaction(session_id(payload), window)
            if (
                payload.get("is_first_compaction") is True
                and window is not None
                and window < LARGE_CONTEXT_WINDOW
            ):
                return json.dumps(
                    {
                        "user_message": (
                            f"Context compacted at {window:,} tokens. Cursor cannot "
                            "switch context windows automatically; "
                            "switch to a 1M-context model to reduce repeated compactions."
                        )
                    }
                )
    except json.JSONDecodeError:
        pass
    return "{}"


def main() -> None:
    raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
    sys.stdout.write(output_for(raw))


if __name__ == "__main__":
    main()

