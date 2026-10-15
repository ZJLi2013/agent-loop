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


_TARGET = re.compile(r"(\]\()([^)\s]+)(\))")
_ANCHOR_LINE = re.compile(r'^<a id="([^"]+)"></a>\s*$')


def _local(target: str) -> tuple[str, str] | None:
    if re.match(r"^[a-z][a-z0-9+.-]*:", target, re.I):
        return None
    name, _, anchor = target.partition("#")
    return name, anchor


def _rewrite(text: str, change) -> str:
    def replace(match: re.Match[str]) -> str:
        parts = _local(match.group(2))
        new = change(*parts) if parts else None
        return f"{match.group(1)}{new}{match.group(3)}" if new else match.group(0)

    return _TARGET.sub(replace, text)


def _relpath(path: Path, base: Path) -> str:
    return Path(os.path.relpath(path.resolve(), base.resolve())).as_posix()


def _relink(text: str, source: Path, target: Path) -> str:
    def change(name: str, anchor: str) -> str | None:
        if not name:
            return None
        moved = _relpath(source / name, target)
        return f"{moved}#{anchor}" if anchor else moved

    return _rewrite(text, change)


def _retarget(text: str, base: Path, plan: Path, archive: Path, moved: set[str]) -> str:
    def change(name: str, anchor: str) -> str | None:
        if anchor not in moved or (base / name).resolve() != plan.resolve():
            return None
        return f"{_relpath(archive, base)}#{anchor}"

    return _rewrite(text, change)


def _task_sections(lines: list[str], task_id: str) -> list[tuple[int, int]]:
    spans = []
    for index, line in enumerate(lines):
        match = _HEADING.match(line)
        if not match or re.split(r"[\s:：]", match.group(2).strip(), maxsplit=1)[0] != task_id:
            continue
        start = index - 1 if index and _ANCHOR_LINE.match(lines[index - 1]) else index
        end = next(
            (
                later
                for later in range(index + 1, len(lines))
                if _ANCHOR_LINE.match(lines[later])
                or (
                    (heading := _HEADING.match(lines[later]))
                    and len(heading.group(1)) <= len(match.group(1))
                )
            ),
            len(lines),
        )
        spans.append((start, end))
    return spans


def _mark_done(root: Path, task_id: str) -> None:
    active = task_file(root)
    if not active.exists():
        return
    lines = active.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        cells = _cells(line)
        if cells and len(cells) >= 6 and _task_id(line) == task_id and not _closed(line):
            cells[5] = "✅ done"
            lines[index] = "| " + " | ".join(cells) + " |"
            _atomic_write(active, "\n".join(lines) + "\n")
            return


def _move_sections(root: Path, plan: Path, task_id: str, review: str | None) -> None:
    archive = plan.with_name(f"{plan.stem}-archive{plan.suffix}")
    lines = plan.read_text(encoding="utf-8").splitlines()
    spans = _task_sections(lines, task_id)
    if not spans and not review:
        return
    moved_lines = [line for start, end in spans for line in lines[start:end]]
    anchors = [m.group(1) for line in moved_lines if (m := _ANCHOR_LINE.match(line))]
    moved = set(anchors)

    kept = [
        line
        for index, line in enumerate(lines)
        if not any(start <= index < end for start, end in spans)
    ]
    if spans:
        link = f"{archive.name}#{anchors[0]}" if anchors else archive.name
        kept.insert(spans[0][0], f"{task_id} 的设计、结果与 review 依据见 [归档]({link})。")

    def to_archive(name: str, anchor: str) -> str | None:
        return f"{archive.name}#{anchor}" if not name and anchor in moved else None

    def into_archive(name: str, anchor: str) -> str | None:
        if not name:
            return f"{plan.name}#{anchor}" if anchor not in moved else None
        if anchor in moved and (plan.parent / name).resolve() == plan:
            return f"#{anchor}"
        return None

    def within_archive(name: str, anchor: str) -> str | None:
        return into_archive(name, anchor) if name else None

    body = _retarget(_rewrite("\n".join(kept), to_archive), plan.parent, plan, archive, moved)
    section = _rewrite("\n".join(moved_lines), into_archive).strip()
    if review:
        section = f"{section}\n\n### {task_id} boundary review\n\n{review.strip()}".strip()
    existing = archive.read_text(encoding="utf-8").rstrip() if archive.exists() else ""
    existing = _rewrite(existing, within_archive)
    _atomic_write(archive, f"{existing}\n\n{section}\n".lstrip("\n"))
    _atomic_write(plan, body.rstrip() + "\n")

    if not moved:
        return
    for doc in runtime_dir(root).rglob("*.md"):
        if doc.resolve() in {plan, archive.resolve()}:
            continue
        text = doc.read_text(encoding="utf-8")
        updated = _retarget(text, doc.parent, plan, archive, moved)
        if updated != text:
            _atomic_write(doc, updated)


def close_task(root: Path, plan_doc: str | None, task_id: str, review: str | None) -> None:
    _mark_done(root, task_id)
    if plan_doc and (root / plan_doc).is_file():
        _move_sections(root, (root / plan_doc).resolve(), task_id, review)
    archive_closed_tasks(root)


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
    closed_rows = [
        _relink(line, active_path.parent, archive_path.parent) for line in closed_rows
    ]
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
