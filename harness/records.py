from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from harness.project import runtime_dir, task_file

ARCHIVE_DIR = "archive"
TASK_ARCHIVE = "tasks.md"
CLOSED_MARKERS = ("✅ done", "❌ dropped")
_LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")


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


def open_task_ids(root: Path) -> list[str]:
    path = task_file(root)
    if not path.exists():
        return []
    return [
        task_id
        for line in path.read_text(encoding="utf-8").splitlines()
        if (task_id := _task_id(line))
        and (cells := _cells(line))
        and len(cells) >= 6
        and not _closed(line)
    ]


def task_row(root: Path, task_id: str) -> list[str] | None:
    path = task_file(root)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = _cells(line)
        if cells and len(cells) >= 6 and _task_id(line) == task_id:
            return cells
    return None


def _slug(text: str) -> str:
    return re.sub(r"[^\w\- ]", "", text.strip().lower()).replace(" ", "-")


def _section(text: str, anchor: str) -> str:
    if not anchor:
        return text
    lines = text.splitlines()
    start = next(
        (
            index
            for index, line in enumerate(lines)
            if line.strip() == f'<a id="{anchor}"></a>'
            or ((match := _HEADING.match(line)) and _slug(match.group(2)) == anchor)
        ),
        None,
    )
    if start is None:
        return ""
    heading = next(
        (index for index in range(start, len(lines)) if _HEADING.match(lines[index])),
        None,
    )
    if heading is None:
        return "\n".join(lines[start:])
    level = len(_HEADING.match(lines[heading]).group(1))
    end = next(
        (
            index
            for index in range(heading + 1, len(lines))
            if lines[index].strip().startswith("<a id=")
            or (
                (match := _HEADING.match(lines[index]))
                and len(match.group(1)) <= level
            )
        ),
        len(lines),
    )
    return "\n".join(lines[start:end])


def task_digest(root: Path, task_id: str) -> str | None:
    cells = task_row(root, task_id)
    if cells is None:
        return None
    base = task_file(root).parent
    digest = hashlib.sha256()
    for part in (cells[3], cells[4]):
        digest.update(part.encode("utf-8") + b"\0")
    for target in _LINK.findall(cells[4]):
        name, _, anchor = target.partition("#")
        if "://" in name or not name.endswith(".md"):
            continue
        try:
            text = (base / name).read_text(encoding="utf-8")
        except OSError:
            text = ""
        digest.update(target.encode("utf-8") + b"\0")
        digest.update(_section(text, anchor).encode("utf-8") + b"\0")
    return digest.hexdigest()[:16]


def active_task_status(root: Path, task_id: str) -> str | None:
    cells = task_row(root, task_id)
    return cells[5] if cells else None


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
