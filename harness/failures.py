"""Consecutive failure counts per task; the only reader and writer of `.harness/failures.json`."""
from __future__ import annotations

import contextlib
from pathlib import Path
from typing import Any, Callable, Iterator

from harness.storage import atomic_write_json, harness_dir, read_json, state_lock, utc_now

FAILURES_FILE = "failures.json"


def _path(root: Path) -> Path:
    return harness_dir(root) / FAILURES_FILE


def _load(root: Path) -> dict[str, Any]:
    path = _path(root)
    data = read_json(path) if path.exists() else {}
    data.setdefault("tasks", {})
    data.setdefault("imports", [])
    return data


@contextlib.contextmanager
def _locked(root: Path, held: bool) -> Iterator[None]:
    if held:
        yield
    else:
        with state_lock(root):
            yield


def _update(root: Path, held: bool, change: Callable[[dict[str, Any]], Any]) -> Any:
    with _locked(root, held):
        data = _load(root)
        result = change(data)
        atomic_write_json(_path(root), data)
        return result


def _entry(data: dict[str, Any], task_id: str) -> dict[str, Any]:
    return data["tasks"].setdefault(task_id, {"count": 0, "notes": []})


def count(root: Path, task_id: str) -> int:
    return int(_load(root)["tasks"].get(task_id, {}).get("count", 0))


def add(root: Path, task_id: str, note: str) -> int:
    def change(data: dict[str, Any]) -> int:
        entry = _entry(data, task_id)
        entry["count"] += 1
        entry["notes"].append({"at": utc_now(), "note": note, "source": "fail"})
        return entry["count"]

    return _update(root, False, change)


def reset(root: Path, task_id: str, *, held: bool = False) -> None:
    """Clear the count after the locked verifier passes; notes stay."""
    if not count(root, task_id):
        return

    def change(data: dict[str, Any]) -> None:
        entry = _entry(data, task_id)
        entry["count"] = 0
        entry["notes"].append({"at": utc_now(), "note": "locked verifier passed", "source": "verify"})

    _update(root, held, change)


def import_counts(root: Path, digest: str, counts: dict[str, int]) -> bool:
    """Set the counts a migration read from the failure column, once per migration input."""
    def change(data: dict[str, Any]) -> bool:
        if digest in data["imports"]:
            return False
        for task_id, value in counts.items():
            entry = _entry(data, task_id)
            entry["count"] = value
            entry["notes"].append({"at": utc_now(), "note": f"migrated from task.md ({digest[:12]})", "source": "migrate"})
        data["imports"].append(digest)
        return True

    return _update(root, False, change)


def take(root: Path, task_id: str, *, held: bool = False) -> int:
    """Remove the task's entry at CLOSE, after its count is in the archive row."""
    if task_id not in _load(root)["tasks"]:
        return 0
    return _update(root, held, lambda data: int(data["tasks"].pop(task_id, {}).get("count", 0)))
