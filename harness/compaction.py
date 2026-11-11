from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path

LARGE_CONTEXT_WINDOW = 1_000_000
_MARKS = Path(tempfile.gettempdir()) / "agent-loop-compactions"


def _mark(session_id: str) -> Path:
    return _MARKS / hashlib.sha256(session_id.encode()).hexdigest()


def record_compaction(session_id: str | None, window: int | None = None) -> None:
    if session_id is None:
        return
    try:
        _MARKS.mkdir(parents=True, exist_ok=True)
        _mark(session_id).write_text(str(window or ""), encoding="utf-8")
    except OSError:
        pass


def handoff_mode(session_id: str | None) -> str | None:
    if os.environ.get("AGENT_LOOP_SESSION_HOST"):
        return "host"
    if session_id is None:
        return None
    try:
        window = _mark(session_id).read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if window.isdigit() and int(window) < LARGE_CONTEXT_WINDOW:
        return "new_session_1m"
    return "new_session"
