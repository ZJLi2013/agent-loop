from __future__ import annotations

import shutil
from pathlib import Path

from harness.errors import HarnessError
from harness.plan import PAUSE_FILE
from harness.storage import (
    CONFIG_FILE,
    HARNESS_DIR,
    JOURNAL_FILE,
    LOCK_FILE,
    STATE_FILE,
    harness_dir,
)

TASKS_DIR = "tasks"


def scratch_path(task_id: str) -> str:
    return f"{HARNESS_DIR}/{TASKS_DIR}/{task_id}"


def task_dir(root: Path, task_id: str) -> Path:
    if not task_id or task_id in {".", ".."} or Path(task_id).name != task_id:
        raise HarnessError(f"task id {task_id!r} must be a single path segment")
    return harness_dir(root) / TASKS_DIR / task_id


def clean_task(root: Path, task_id: str) -> str | None:
    path = task_dir(root, task_id)
    try:
        shutil.rmtree(path)
    except FileNotFoundError:
        pass
    except OSError as exc:
        return f"cannot remove {scratch_path(task_id)}: {exc}"
    return None


def strays(root: Path, task_id: str) -> list[str]:
    from harness.page import PAGER_STATE
    from harness.plan_review import PLAN_REVIEW_DIR
    from harness.review import REVIEW_DIR

    owned = {
        CONFIG_FILE,
        STATE_FILE,
        JOURNAL_FILE,
        LOCK_FILE,
        PAUSE_FILE,
        PAGER_STATE,
        PLAN_REVIEW_DIR,
        REVIEW_DIR,
        TASKS_DIR,
        "artifacts",
    }
    base = harness_dir(root)
    found = [
        entry.name
        for entry in base.iterdir()
        if entry.name not in owned
        and not (entry.name.startswith(".") and entry.name.endswith(".tmp"))
    ]
    tasks = base / TASKS_DIR
    if tasks.is_dir():
        found += [f"{TASKS_DIR}/{entry.name}" for entry in tasks.iterdir() if entry.name != task_id]
    return sorted(found)
