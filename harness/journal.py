from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import shutil
import uuid
from pathlib import Path
from typing import Any

from harness.storage import JOURNAL_FILE, harness_dir

_SECRET_RE = re.compile(
    r"(?i)\b(api[_-]?key|token|password|secret|authorization)"
    r"(\s*[:=]\s*)([^\s,;]+)"
)


def new_run_id() -> str:
    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _bounded_text(path: Path, cap: int) -> tuple[str, bool]:
    size = path.stat().st_size
    if size <= cap:
        data = path.read_bytes()
        truncated = False
    else:
        half = max(1, cap // 2)
        with path.open("rb") as fh:
            head = fh.read(half)
            fh.seek(max(0, size - half))
            tail = fh.read(half)
        data = head + b"\n... output truncated ...\n" + tail
        truncated = True
    text = data.decode("utf-8", errors="replace")
    return _SECRET_RE.sub(r"\1\2***REDACTED***", text), truncated


def write_artifact(
    destination: Path,
    source: Path,
    cap: int,
) -> tuple[str, bool]:
    text, truncated = _bounded_text(source, cap)
    destination.write_text(text, encoding="utf-8")
    return _sha256_file(source), truncated


def append_journal(root: Path, result: dict[str, Any], limit: int) -> None:
    path = harness_dir(root) / JOURNAL_FILE
    summary = {
        key: result[key]
        for key in (
            "run_id",
            "task_id",
            "kind",
            "argv",
            "started_at",
            "duration_seconds",
            "timed_out",
            "exit_code",
            "outcome",
        )
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(summary, ensure_ascii=False) + "\n")
    lines = path.read_text(encoding="utf-8").splitlines()
    if len(lines) > limit:
        path.write_text("\n".join(lines[-limit:]) + "\n", encoding="utf-8")


def prune_artifacts(root: Path, limit: int) -> None:
    artifacts = harness_dir(root) / "artifacts"
    runs = sorted(
        (path for path in artifacts.iterdir() if path.is_dir()),
        key=lambda path: path.stat().st_mtime_ns,
    )
    for old in runs[:-limit]:
        shutil.rmtree(old, ignore_errors=True)

