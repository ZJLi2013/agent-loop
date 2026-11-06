from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from harness.errors import HarnessError
from harness.project import RUNTIME_DIR, runtime_dir, task_file
from harness.storage import STATE_FILE, harness_dir, load_runtime

ARCHIVE_DIR = "archive"
TASK_ARCHIVE = "tasks.md"
PROGRESS_FILE = "progress.md"
# Records with their own retirement rules; leftovers never reports them.
RETIRED_ELSEWHERE = {
    "task.md",
    PROGRESS_FILE,
    "memory",
    ARCHIVE_DIR,
    "reviewer.json",
    "pager.json",
    "review-checklist.md",
    "reports",
}
CLOSED_MARKERS = ("✅ done", "❌ dropped")
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")


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
    # Mainline rows have five cells and stay in task.md after their Goal is done.
    return bool(
        cells
        and len(cells) >= 6
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


def active_task_status(root: Path, task_id: str) -> str | None:
    cells = task_row(root, task_id)
    return cells[5] if cells else None


_MAINLINE = re.compile(r"^## 主线[ \t]*$(.*?)(?=^## |\Z)", re.M | re.S)
_MAINLINE_STATUSES = ("✅ done", "▶ next", "⬜ todo")


def mainline_handoff(root: Path, previous_plan: str | None, plan_doc: str) -> bool:
    path = task_file(root)
    if not previous_plan or not path.exists():
        return False
    section = _MAINLINE.search(path.read_text(encoding="utf-8"))
    if not section or not re.search(r"^Mainline Review:\s*approved\s*$", section.group(1), re.M):
        return False
    rows = [
        cells
        for line in section.group(1).splitlines()
        if (cells := _cells(line)) and len(cells) == 5 and cells[3] in _MAINLINE_STATUSES
    ]
    statuses = [cells[3] for cells in rows]
    if statuses.count("▶ next") != 1:
        return False
    index = statuses.index("▶ next")
    if index == 0 or any(status != "✅ done" for status in statuses[:index]):
        return False

    def plan_of(cells: list[str]) -> Path | None:
        link = _TARGET.search(cells[4])
        parts = _local(link.group(2)) if link else None
        return (path.parent / parts[0]).resolve() if parts and parts[0] else None

    previous, following = plan_of(rows[index - 1]), plan_of(rows[index])
    return (
        previous == (root / previous_plan).resolve()
        and following == (root / plan_doc).resolve()
        and previous != following
    )


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


def _structural_lines(lines: list[str]) -> list[bool]:
    structural = []
    marker: str | None = None
    minimum = 0
    for line in lines:
        if marker is not None:
            structural.append(False)
            stripped = line.lstrip(" ")
            indent = len(line) - len(stripped)
            candidate = stripped.rstrip(" \t")
            if (
                indent <= 3
                and len(candidate) >= minimum
                and set(candidate) == {marker}
            ):
                marker = None
            continue

        match = _FENCE.match(line)
        if match and not (
            match.group("marker").startswith("`")
            and "`" in match.group("info")
        ):
            structural.append(False)
            marker = match.group("marker")[0]
            minimum = len(match.group("marker"))
        else:
            structural.append(True)
    return structural


def _task_sections(lines: list[str], task_id: str) -> list[tuple[int, int]]:
    spans = []
    structural = _structural_lines(lines)
    for index, line in enumerate(lines):
        if not structural[index]:
            continue
        match = _HEADING.match(line)
        if not match or re.split(r"[\s:：]", match.group(2).strip(), maxsplit=1)[0] != task_id:
            continue
        start = (
            index - 1
            if index
            and structural[index - 1]
            and _ANCHOR_LINE.match(lines[index - 1])
            else index
        )
        end = next(
            (
                later
                for later in range(index + 1, len(lines))
                if structural[later]
                and (
                    _ANCHOR_LINE.match(lines[later])
                    or (
                        (heading := _HEADING.match(lines[later]))
                        and len(heading.group(1)) <= len(match.group(1))
                    )
                )
            ),
            len(lines),
        )
        spans.append((start, end))
    return spans


def _slug(heading: str) -> str:
    return re.sub(r"[^\w\- ]", "", heading.strip().lower()).replace(" ", "-")


def design_location_error(root: Path, task_id: str, plan_doc: str) -> str | None:
    plan = (root / plan_doc).resolve()
    lines = plan.read_text(encoding="utf-8").splitlines() if plan.is_file() else []
    structural = _structural_lines(lines)
    archived = set()
    for start, end in _task_sections(lines, task_id):
        for index in range(start, end):
            if not structural[index]:
                continue
            if anchor := _ANCHOR_LINE.match(lines[index]):
                archived.add(anchor.group(1))
            elif heading := _HEADING.match(lines[index]):
                archived.add(_slug(heading.group(2)))

    base = task_file(root).parent
    located, stray = False, []
    for match in _TARGET.finditer(" | ".join(task_row(root, task_id) or [])):
        parts = _local(match.group(2))
        if not parts or not parts[0]:
            continue
        target = (base / unquote(parts[0])).resolve()
        if target == plan:
            if unquote(parts[1]) in archived:
                located = True
            else:
                stray.append(match.group(2))
        elif target.is_file() and target.is_relative_to(plan.parent):
            located = True
    if located and not stray:
        return None
    found = f" (not archivable: {', '.join(stray)})" if stray else ""
    return (
        f"task {task_id} must link its design to a {plan_doc} section whose heading starts "
        f"with {task_id} (add <a id> before it if the slug differs) or to a file under "
        f"{plan.parent.name}/; CLOSE archives only those{found}"
    )


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


def _handoff_starts(lines: list[str]) -> list[int]:
    structural = _structural_lines(lines)
    return [i for i, line in enumerate(lines) if structural[i] and line.startswith("## ")]


def _newest_handoff(text: str) -> str:
    lines = text.splitlines()
    starts = _handoff_starts(lines)
    return "\n".join(lines[: starts[1]]) if len(starts) > 1 else text


def archive_progress(root: Path, now: datetime | None = None) -> tuple[int, str | None]:
    """Keep the newest handoff in progress.md and append the rest to this month's archive."""
    path = runtime_dir(root) / PROGRESS_FILE
    try:
        lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
        starts = _handoff_starts(lines)
        if len(starts) < 2:
            return 0, None
        bounds = [*starts[1:], len(lines)]
        sections = ["\n".join(lines[a:b]) for a, b in zip(bounds, bounds[1:])]
        archive = path.parent / ARCHIVE_DIR / f"progress-{(now or datetime.now()):%Y-%m}.md"
        existing = archive.read_text(encoding="utf-8").rstrip() if archive.exists() else ""
        # A failed replace leaves sections that are already archived; append each once.
        new = [section for section in sections if section.strip() not in existing]
        if new:
            appended = "\n".join(new).rstrip()
            _atomic_write(archive, f"{existing}\n\n{appended}\n" if existing else f"{appended}\n")
        _atomic_write(path, "\n".join(lines[: starts[1]]).rstrip() + "\n")
    except OSError as exc:
        return 0, f"cannot archive {PROGRESS_FILE}: {exc}"
    return len(sections), None


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return ""


def _linked_files(text: str, base: Path) -> set[Path]:
    found = set()
    for match in _TARGET.finditer(text):
        parts = _local(match.group(2))
        if parts and parts[0] and (target := (base / unquote(parts[0])).resolve()).is_file():
            found.add(target)
    return found


def leftovers(root: Path) -> list[dict[str, str]]:
    """List .agent-loop files tied to closed tasks or Goals that no current document mentions."""
    base = runtime_dir(root)
    if base.name != RUNTIME_DIR or not base.is_dir():
        return []
    locked: set[Path] = set()
    if (harness_dir(root) / STATE_FILE).exists():
        try:
            config, state = load_runtime(root)
        except HarnessError:
            # Which verifier is locked is unknown; a deleted locked verifier turns the evidence stale.
            return []
        if state.get("active"):
            locked = {(root / name).resolve() for name in config["verifier"].get("files") or {}}
    tasks = task_file(root)
    task_text = _read(tasks)
    closed = {i.lower() for i in archived_task_ids(root)} - {i.lower() for i in open_task_ids(root)}

    done_plans: set[Path] = set()
    live_plans: set[Path] = set()
    section = _MAINLINE.search(task_text)
    for line in (section.group(1) if section else "").splitlines():
        cells = _cells(line)
        if cells and len(cells) >= 5:
            plans = _linked_files(" | ".join(cells), tasks.parent)
            done = any(cell.startswith("✅") for cell in cells)
            (done_plans if done else live_plans).update(plans)
    for line in task_text.splitlines():
        cells = _cells(line)
        if cells and len(cells) >= 6 and not _closed(line):
            live_plans |= _linked_files(" | ".join(cells), tasks.parent)
    live_plans -= done_plans
    # Only a plan's own directory under .agent-loop/ scopes its Goal; a plan at the top or outside scopes nothing.
    plan_dirs = {plan.parent: plan for plan in live_plans if base in plan.parent.parents}
    plan_dirs.update(
        {
            plan.parent: plan
            for plan in done_plans
            if base in plan.parent.parents and plan.parent not in plan_dirs
        }
    )

    current = "\n".join(
        [
            task_text,
            _newest_handoff(_read(base / PROGRESS_FILE)),
            *(_read(path) for path in sorted((base / "memory").glob("*.md"))),
            *(_read(path) for path in sorted(base.glob("*.json"))),
            *(_read(path) for path in sorted(live_plans)),
        ]
    )

    files = [
        path
        for path in base.rglob("*")
        if path.is_file() and path.relative_to(base).parts[0] not in RETIRED_ELSEWHERE
    ]
    plan_docs = done_plans | live_plans
    reasons: dict[Path, list[str]] = {}
    for path in files:
        relative = path.relative_to(base)
        resolved = path.resolve()
        if (
            resolved in plan_docs
            or resolved in locked
            or path.stem.endswith("-archive")
            or {"sub-exp", ARCHIVE_DIR} & set(relative.parts[:-1])
        ):
            continue
        why = [
            f"closed task {task_id}"
            for task_id in sorted(closed)
            if re.search(rf"(?<![a-z]){re.escape(task_id)}(?![a-z0-9])", path.stem.lower())
        ]
        owner = next((plan_dirs[d] for d in resolved.parents if d in plan_dirs), None)
        if owner in done_plans:
            why.append(f"closed Goal plan {owner.relative_to(base).as_posix()}")
        if why and path.name not in current and relative.as_posix() not in current:
            reasons[path] = why

    totals: dict[Path, list[int]] = {}
    for path in files:
        for parent in path.parents:
            if parent == base:
                break
            counts = totals.setdefault(parent, [0, 0])
            counts[0] += 1
            counts[1] += path in reasons
    stale = {d for d, (total, hits) in totals.items() if total == hits}

    report: dict[str, set[str]] = {}
    for path, why in reasons.items():
        top = next((d for d in reversed(path.parents) if d in stale), None)
        key = (
            f"{RUNTIME_DIR}/{top.relative_to(base).as_posix()}/"
            if top
            else f"{RUNTIME_DIR}/{path.relative_to(base).as_posix()}"
        )
        report.setdefault(key, set()).update(why)
    return [{"path": key, "why": ", ".join(sorted(whys))} for key, whys in sorted(report.items())]
