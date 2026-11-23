from __future__ import annotations

import os
import re
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import unquote

from harness import failures
from harness.errors import HarnessError
from harness.project import RUNTIME_DIR, memory_dir, runtime_dir, task_file
from harness.storage import STATE_FILE, harness_dir, load_runtime

ARCHIVE_DIR = "archive"
SUB_EXP = "sub-exp"
FEATURES_DIR = "features"
EXPS_DIR = "exps"
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
TASK_COLUMNS = 4
# The archive keeps the 7-column rows it always had; CLOSE writes `—` as their priority.
ARCHIVE_HEADER = "| P | id | rev | task | 验收检查点 | 状态 | 失败 |\n|---|---|---|---|---|---|---|"
ARCHIVE_COLUMNS = 7
_HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
_FENCE = re.compile(r"^ {0,3}(?P<marker>`{3,}|~{3,})(?P<info>.*)$")
_REVISION_LINE = re.compile(r"^\s*-\s*rev[：:]\s*(\S+)\s*$")


def _cells(line: str) -> list[str] | None:
    stripped = line.strip()
    if not stripped.startswith("|") or not stripped.endswith("|"):
        return None
    return [cell.strip() for cell in stripped.strip("|").split("|")]


def _separator(cells: list[str]) -> bool:
    return all(set(cell) <= {"-", ":"} for cell in cells)


def _task_rows(lines: list[str]) -> list[tuple[int, list[str]]]:
    """Rows of the tables whose header is `| id | task | 验收检查点 | 状态 |`."""
    rows = []
    header: list[str] | None = None
    for index, line in enumerate(lines):
        cells = _cells(line)
        if cells is None:
            header = None
        elif header is None:
            header = cells
        elif (
            header[0].lower() == "id"
            and len(header) == len(cells) == TASK_COLUMNS
            and cells[0]
            and not _separator(cells)
        ):
            rows.append((index, cells))
    return rows


def _archive_rows(lines: list[str]) -> list[tuple[int, list[str]]]:
    return [
        (index, cells)
        for index, line in enumerate(lines)
        if (cells := _cells(line))
        and len(cells) >= ARCHIVE_COLUMNS
        and cells[1]
        and cells[1].lower() != "id"
        and not _separator(cells)
    ]


def _closed(cells: list[str]) -> bool:
    return cells[3].startswith(CLOSED_MARKERS)


def _active_lines(root: Path) -> list[str]:
    path = task_file(root)
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def legacy_task_table(root: Path) -> bool:
    """task.md still has a `| P | id | rev | ... |` table, which only migrate-tasks converts."""
    return any(
        (cells := _cells(line)) and len(cells) == ARCHIVE_COLUMNS and cells[:2] == ["P", "id"]
        for line in _active_lines(root)
    )


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def _archive_path(root: Path) -> Path:
    return runtime_dir(root) / ARCHIVE_DIR / TASK_ARCHIVE


def _archive_lines(root: Path) -> list[str]:
    path = _archive_path(root)
    return path.read_text(encoding="utf-8").splitlines() if path.exists() else []


def archived_task_ids(root: Path) -> set[str]:
    return {cells[1] for _, cells in _archive_rows(_archive_lines(root))}


def archived_revision(root: Path, task_id: str) -> str | None:
    """The rev cell of the newest archive row of task_id; ids restart across Goals."""
    found = [cells[2] for _, cells in _archive_rows(_archive_lines(root)) if cells[1] == task_id]
    return found[-1] if found else None


def task_ids(root: Path) -> set[str]:
    """Every task id in task.md, open or closed, and in the task archive."""
    return {cells[0] for _, cells in _task_rows(_active_lines(root))} | archived_task_ids(root)


def feature_doc(root: Path, plan: Path) -> bool:
    return plan.parent == (root / FEATURES_DIR).resolve()


def _belongs(root: Path, plan: Path, target: Path) -> bool:
    """A feature document owns only links to itself; a legacy plan owns its whole directory."""
    return target == plan if feature_doc(root, plan) else target.is_relative_to(plan.parent)


def open_task_ids(root: Path, *, plan_doc: str | None = None) -> list[str]:
    path = task_file(root)
    lines = _active_lines(root)
    plan = (root / plan_doc).resolve() if plan_doc else None
    return [
        cells[0]
        for index, cells in _task_rows(lines)
        if not _closed(cells)
        and (plan is None or any(_belongs(root, plan, target) for target in _linked_files(lines[index], path.parent)))
    ]


def task_links(root: Path, task_ids: list[str]) -> set[Path]:
    path = task_file(root)
    lines = _active_lines(root)
    return {
        target
        for index, cells in _task_rows(lines)
        if cells[0] in task_ids
        for target in _linked_files(lines[index], path.parent)
    }


def task_row(root: Path, task_id: str) -> list[str] | None:
    return next((cells for _, cells in _task_rows(_active_lines(root)) if cells[0] == task_id), None)


def active_task_status(root: Path, task_id: str) -> str | None:
    cells = task_row(root, task_id)
    return cells[3] if cells else None


def design_spans(root: Path, task_id: str, row: str | None = None) -> list[tuple[Path, int, int]]:
    """The task's design: its sections in the markdown its row links, or a whole linked sub-exp file."""
    path = task_file(root)
    if row is None:
        lines = _active_lines(root)
        row = next((lines[index] for index, cells in _task_rows(lines) if cells[0] == task_id), None)
    spans = []
    for target in sorted(_linked_files(row or "", path.parent)):
        if target.suffix.lower() != ".md":
            continue
        text = target.read_text(encoding="utf-8").splitlines()
        found = _task_sections(text, task_id)
        if not found and SUB_EXP in target.parent.parts:
            found = [(0, len(text))]
        spans += [(target, start, end) for start, end in found]
    return spans


def design_revision(root: Path, task_id: str) -> str | None:
    """The `- rev：rN` line of the active task's design, None when it has none."""
    for target, start, end in design_spans(root, task_id):
        lines = target.read_text(encoding="utf-8").splitlines()
        structural = _structural_lines(lines)
        for index in range(start, end):
            if structural[index] and (match := _REVISION_LINE.match(lines[index])):
                return match.group(1)
    return None


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

    previous, following = (_linked_files(rows[i][4], path.parent) for i in (index - 1, index))
    return (
        (root / previous_plan).resolve() in previous
        and (root / plan_doc).resolve() in following
        and not previous & following
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


_LINK = re.compile(r"\[([^\]]*)\]\(([^)\s]+)\)")


def _unlink(text: str, doc: Path, plan: Path, dropped: set[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        parts = _local(match.group(2))
        if not parts:
            return match.group(0)
        name, anchor = parts
        target = (doc.parent / unquote(name)).resolve() if name else doc.resolve()
        if unquote(anchor) in dropped and target == plan.resolve():
            return match.group(1)
        return match.group(0)

    return _LINK.sub(replace, text)


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


def _in_flight(root: Path, text: str) -> bool:
    """A plan that names an archived task has closed one, so its Goal started before the features/ layout."""
    return any(re.search(rf"(?<![\w-]){re.escape(task_id)}(?![\w-])", text) for task_id in archived_task_ids(root))


def design_location_error(root: Path, task_id: str, plan_doc: str) -> str | None:
    plan = (root / plan_doc).resolve()
    text = plan.read_text(encoding="utf-8") if plan.is_file() else ""
    feature = feature_doc(root, plan)
    if not feature and not _in_flight(root, text):
        return (
            f"plan document {plan_doc} must be {FEATURES_DIR}/<feature>.md, directly under {FEATURES_DIR}/; "
            f"a plan elsewhere is accepted only after one of its tasks is archived"
        )
    lines = text.splitlines()
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
        elif not feature and target.is_file() and target.is_relative_to(plan.parent / SUB_EXP):
            located = True
    if located and not stray:
        return None
    found = f" (not a task section: {', '.join(stray)})" if stray else ""
    return (
        f"task {task_id} must link its design to a {plan_doc} section whose heading starts "
        f"with {task_id} (add <a id> before it if the slug differs); {EXPS_DIR}/ and other "
        f"documents hold results, not designs{found}"
    )


def _mark_done(root: Path, task_id: str) -> None:
    active = task_file(root)
    lines = _active_lines(root)
    for index, cells in _task_rows(lines):
        if cells[0] == task_id and not _closed(cells):
            cells[3] = "✅ done"
            lines[index] = "| " + " | ".join(cells) + " |"
            _atomic_write(active, "\n".join(lines) + "\n")
            return


def _drop_sections(root: Path, plan: Path, task_id: str) -> None:
    lines = plan.read_text(encoding="utf-8").splitlines()
    spans = _task_sections(lines, task_id)
    if not spans:
        return
    structural = _structural_lines(lines)
    dropped = set()
    for start, end in spans:
        for index in range(start, end):
            if not structural[index]:
                continue
            if anchor := _ANCHOR_LINE.match(lines[index]):
                dropped.add(anchor.group(1))
            elif heading := _HEADING.match(lines[index]):
                dropped.add(_slug(heading.group(2)))
    kept = [
        line
        for index, line in enumerate(lines)
        if not any(start <= index < end for start, end in spans)
    ]
    _atomic_write(plan, _unlink("\n".join(kept), plan, plan, dropped).rstrip() + "\n")

    docs = [*runtime_dir(root).rglob("*.md"), *(root / FEATURES_DIR).glob("*.md"), *(root / EXPS_DIR).glob("*.md")]
    for doc in docs:
        if doc.resolve() == plan:
            continue
        text = doc.read_text(encoding="utf-8")
        updated = _unlink(text, doc, plan, dropped)
        if updated != text:
            _atomic_write(doc, updated)


def close_task(root: Path, plan_doc: str | None, task_id: str) -> None:
    """Caller holds state_lock. Each step is safe to rerun, so an interrupted CLOSE completes on the next one."""
    _mark_done(root, task_id)
    closed = _archive_closed(root)
    if plan_doc and (root / plan_doc).is_file():
        _drop_sections(root, (root / plan_doc).resolve(), task_id)
    _remove_closed(root)
    for closed_id in {task_id, *closed}:
        failures.take(root, closed_id, held=True)


def _archive_closed(root: Path) -> list[str]:
    """Append every closed row of task.md to the archive with its rev and failure count."""
    active_path = task_file(root)
    closed = [cells for _, cells in _task_rows(_active_lines(root)) if _closed(cells)]
    if not closed:
        return []
    archive_path = _archive_path(root)
    if archive_path.exists():
        archive = archive_path.read_text(encoding="utf-8").rstrip()
    else:
        archive = "\n".join(["# Closed Tasks", "", "这些行只用于追溯，不参与 SELECT。", "", ARCHIVE_HEADER])
    rows = []
    for task_id, task, check, status in closed:
        revision = design_revision(root, task_id) or archived_revision(root, task_id) or "—"
        row = f"| — | {task_id} | {revision} | {task} | {check} | {status} | {failures.count(root, task_id)} |"
        rows.append(_relink(row, active_path.parent, archive_path.parent))
    # Task ids restart across Goals; only an identical row is a duplicate.
    existing = {line.strip() for line in archive.splitlines()}
    new_rows = [row for row in rows if row not in existing]
    if new_rows:
        _atomic_write(archive_path, f"{archive}\n" + "\n".join(new_rows) + "\n")
    return [cells[0] for cells in closed]


def _remove_closed(root: Path) -> None:
    active_path = task_file(root)
    lines = _active_lines(root)
    closed = {index for index, cells in _task_rows(lines) if _closed(cells)}
    if not closed:
        return
    active = "\n".join(line for index, line in enumerate(lines) if index not in closed).rstrip()
    if "archive/tasks.md" not in active:
        active = f"{active}\n\nClosed: [archive/tasks.md](archive/tasks.md)"
    _atomic_write(active_path, f"{active}\n")


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
    root = root.resolve()
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
    for _, cells in _task_rows(task_text.splitlines()):
        if not _closed(cells):
            live_plans |= _linked_files(" | ".join(cells), tasks.parent)
    live_plans -= done_plans
    # Only a plan's own directory scopes its Goal; a plan directly in .agent-loop/, at the root or outside it scopes
    # nothing. A directory outside .agent-loop/ needs git to tell the project's own files from leftovers.
    tracked = untracked = None
    if any(base not in plan.parent.parents and root in plan.parent.parents and plan.parent != base for plan in done_plans):
        tracked = _git_files(root, "ls-files", "-z")
        untracked = _git_files(root, "ls-files", "--others", "-z")

    def scopes(directory: Path) -> bool:
        if base in directory.parents:
            return True
        return (tracked is not None and untracked is not None and root in directory.parents
                and directory not in (base, root / FEATURES_DIR))

    plan_dirs = {plan.parent: plan for plan in live_plans if scopes(plan.parent)}
    plan_dirs.update({plan.parent: plan for plan in done_plans if scopes(plan.parent) and plan.parent not in plan_dirs})
    outside = {d for d, plan in plan_dirs.items() if plan in done_plans and base not in d.parents}

    def within_outside(path: Path) -> bool:
        return any(d in path.parents for d in outside) and not {".git", ".harness"} & set(path.relative_to(root).parts)

    current = "\n".join(
        [
            task_text,
            _newest_handoff(_read(base / PROGRESS_FILE)),
            *(_read(path) for path in sorted(memory_dir(root).glob("*.md"))),
            *(_read(path) for path in sorted(base.glob("*.json"))),
            *(_read(path) for path in sorted(live_plans)),
        ]
    )

    files = [
        path
        for path in base.rglob("*")
        if path.is_file() and path.relative_to(base).parts[0] not in RETIRED_ELSEWHERE
    ]
    files += [path for path in untracked or () if within_outside(path)]
    plan_docs = done_plans | live_plans
    reasons: dict[Path, list[str]] = {}
    for path in files:
        relative = path.relative_to(base if base in path.parents else root)
        resolved = path.resolve()
        owner = next((plan_dirs[d] for d in resolved.parents if d in plan_dirs), None)
        if (
            resolved in plan_docs
            or resolved in locked
            or ARCHIVE_DIR in relative.parts[:-1]
            or (owner not in done_plans and (path.stem.endswith("-archive") or "sub-exp" in relative.parts[:-1]))
        ):
            continue
        why = [
            f"closed task {task_id}"
            for task_id in sorted(closed)
            if re.search(rf"(?<![a-z]){re.escape(task_id)}(?![a-z0-9])", path.stem.lower())
        ]
        if owner in done_plans:
            why.append(f"closed Goal plan {owner.relative_to(base if base in owner.parents else root).as_posix()}")
        if why and path.name not in current and relative.as_posix() not in current:
            reasons[path] = why

    totals: dict[Path, list[int]] = {}
    for path in files + [path for path in tracked or () if within_outside(path)]:
        for parent in path.parents:
            if parent in (base, root):
                break
            counts = totals.setdefault(parent, [0, 0])
            counts[0] += 1
            counts[1] += path in reasons
    stale = {d for d, (total, hits) in totals.items() if total == hits}

    report: dict[str, set[str]] = {}
    for path, why in reasons.items():
        top = next((d for d in reversed(path.parents) if d in stale), path)
        if base in path.parents:
            key = f"{RUNTIME_DIR}/{top.relative_to(base).as_posix()}"
        else:
            key = top.relative_to(root).as_posix()
        report.setdefault(key + ("/" if top != path else ""), set()).update(why)
    return [{"path": key, "why": ", ".join(sorted(whys))} for key, whys in sorted(report.items())]


def _git_files(root: Path, *args: str) -> list[Path] | None:
    """Files git lists under root, or None when root is not in a repository with a commit."""
    try:
        head = subprocess.run(["git", "-C", str(root), "rev-parse", "--verify", "-q", "HEAD"], capture_output=True)
        listed = subprocess.run(["git", "-C", str(root), *args], capture_output=True)
    except OSError:
        return None
    if head.returncode or listed.returncode:
        return None
    return [(root / name.decode("utf-8", "surrogateescape")).resolve() for name in listed.stdout.split(b"\0") if name]
