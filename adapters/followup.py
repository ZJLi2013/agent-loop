from __future__ import annotations

import hashlib
import re
import tempfile
from pathlib import Path

_MARKERS = Path(tempfile.gettempdir()) / "agent-loop-followups"


def claim_followup(session_id: str | None, message: str) -> bool:
    if session_id is None:
        return True
    stable_message = re.sub(r"\d+\.\d+s remain", "*s remain", message)
    digest = hashlib.sha256(stable_message.encode()).hexdigest()
    marker = _MARKERS / hashlib.sha256(session_id.encode()).hexdigest()
    try:
        previous = marker.read_text(encoding="utf-8")
    except FileNotFoundError:
        previous = None
    except OSError:
        return True
    if previous == digest:
        return False
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(digest, encoding="utf-8")
    except OSError:
        pass
    return True
