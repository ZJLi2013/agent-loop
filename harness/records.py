from __future__ import annotations

import os
from pathlib import Path

from harness.project import runtime_dir, task_file

ARCHIVE_DIR = "archive"
TASK_ARCHIVE = "tasks.md"
CLOSED_MARKERS = ("✅ done", "❌ dropped")


def _cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _task_id(line: str) -> str | None:
    cells = _cells(line)
    if not cells or len(cells) < 2 or cells[1].lower() == "id":
        return None
    if all(set(cell) <= {"-", ":"} for cell in cells):
        return None
    return cells[1] or None


def _closed(line: str) -> bool:
    cells = _cells(line)
    return bool(
        cells
        and any(
            cell.startswith(marker)
            for cell in cells
            for marker in CLOSED_MARKERS
        )
    )


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def archived_task_ids(root: Path) -> set[str]:
    path = runtime_dir(root) / ARCHIVE_DIR / TASK_ARCHIVE
    if not path.exists():
        return set()
    return {
        task_id
        for line in path.read_text(encoding="utf-8").splitlines()
        if (task_id := _task_id(line))
    }


def archive_closed_tasks(root: Path) -> list[str]:
    active_path = task_file(root)
    if not active_path.exists():
        return []

    text = active_path.read_text(encoding="utf-8")
    lines = text.splitlines()
    closed_rows = [line for line in lines if _closed(line)]
    if not closed_rows:
        return []

    archive_path = runtime_dir(root) / ARCHIVE_DIR / TASK_ARCHIVE
    if archive_path.exists():
        archive = archive_path.read_text(encoding="utf-8").rstrip()
    else:
        table_headers = [
            line
            for line in lines
            if (cells := _cells(line))
            and (cells[1].lower() == "id" or all(set(c) <= {"-", ":"} for c in cells))
        ][:2]
        archive = "\n".join(
            [
                "# Closed Tasks",
                "",
                "这些行只用于追溯，不参与 SELECT。",
                "",
                *table_headers,
            ]
        )
    # Task ids restart across Goals; only an identical row is a duplicate.
    existing = {line.strip() for line in archive.splitlines()}
    new_rows = [line for line in closed_rows if line.strip() not in existing]
    if new_rows:
        archive = f"{archive}\n" + "\n".join(new_rows)
    _atomic_write(archive_path, f"{archive}\n")

    active = "\n".join(line for line in lines if not _closed(line)).rstrip()
    if "archive/tasks.md" not in active:
        active = f"{active}\n\nClosed: [archive/tasks.md](archive/tasks.md)"
    _atomic_write(active_path, f"{active}\n")
    return [task_id for line in closed_rows if (task_id := _task_id(line))]
