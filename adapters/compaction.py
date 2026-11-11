from __future__ import annotations

import hashlib
import tempfile
from pathlib import Path

_MARKS = Path(tempfile.gettempdir()) / "agent-loop-compactions"


def _mark(session_id: str) -> Path:
    return _MARKS / hashlib.sha256(session_id.encode()).hexdigest()


def record_compaction(session_id: str | None) -> None:
    if session_id is None:
        return
    try:
        _MARKS.mkdir(parents=True, exist_ok=True)
        _mark(session_id).touch()
    except OSError:
        pass


def compacted(session_id: str | None) -> bool:
    return session_id is not None and _mark(session_id).is_file()
