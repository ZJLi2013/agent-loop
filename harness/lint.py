from __future__ import annotations

import re
import shutil
import subprocess
from importlib import metadata
from pathlib import Path, PurePosixPath
from typing import Any
from urllib.parse import unquote, urlsplit

from harness.errors import HarnessError
from harness.project import RUNTIME_DIR
from harness.records import EXPS_DIR, FEATURES_DIR, SUB_EXP, TASK_COLUMNS, _task_sections, feature_doc, task_ids
from harness.storage import CONFIG_FILE, HARNESS_DIR, harness_dir, read_json

LINT_ARGV = ["agent-loop-harness", "lint", "--changed"]
ALLOW = "<!-- lint: allow -->"
LEFTOVER = re.compile(r"待验证|待确认|在跑|预计|TBD|TODO")
PENDING = re.compile(r"待\s*human")
DESIGN_STATE = "design-state content belongs in the feature's task section"
PRUNED_DIRS = (HARNESS_DIR, RUNTIME_DIR)
TASK_FILE = f"{RUNTIME_DIR}/task.md"

_HEADING = re.compile(r"^\s{0,3}#{1,6}\s+(.*)$")
_CELL_LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")

_FENCE = re.compile(r"^\s*(```|~~~)")
_CODE_SPAN = re.compile(r"(`+).*?\1")
_INLINE_LINK = re.compile(r"!?\[[^\]]*\]\(\s*<?([^)\s>]+)>?[^)]*\)")
_REFERENCE = re.compile(r"^\s{0,3}\[[^\]]+\]:\s*<?([^\s>]+)>?")
_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,(\d+))? @@")
ENTRY_FIELDS = ("目标", "现状", "下一步")
_FIELD = re.compile(r"^\s*(?:[-*]\s+)?(?:\*\*)?(目标|现状|下一步)(?:\*\*)?\s*[：:]")
_SECTION = re.compile(r"^\s{0,3}##\s")
_INDEX_LINE = re.compile(r"^\s*(?:[-*+]\s|\d+\.\s|\|)")
_WORD = re.compile(r"[^\W\d_]")
EXPERIMENT_LOG = re.compile(r"^\s{0,3}##\s+Experiment Log\s*$")


def _git(root: Path, *args: str) -> str:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
            encoding="utf-8",
        ).stdout
    except (OSError, subprocess.CalledProcessError) as exc:
        detail = (getattr(exc, "stderr", None) or str(exc)).strip()
        raise HarnessError(f"git {' '.join(args)} failed: {detail}") from exc


def lint_config(root: Path) -> dict[str, Any]:
    """Settings `init --lint on` records; raises before init writes anything."""
    if not shutil.which(LINT_ARGV[0]):
        raise HarnessError(
            f"{LINT_ARGV[0]} is not on PATH; install agent-loop or init with --lint off"
        )
    try:
        base = _git(root, "rev-parse", "HEAD").strip()
    except HarnessError as exc:
        raise HarnessError(f"lint needs a git repository with a commit ({exc}); init with --lint off") from exc
    try:
        version: str | None = metadata.version("agent-loop")
    except metadata.PackageNotFoundError:
        version = None
    return {"enabled": True, "base": base, "version": version}


def _config(root: Path) -> dict[str, Any]:
    path = harness_dir(root) / CONFIG_FILE
    return read_json(path) if path.exists() else {}


def _design_state(prose: str, ids: set[str]) -> str | None:
    if heading := _HEADING.match(prose):
        first = re.split(r"[\s:：（(]", heading[1].strip(), maxsplit=1)[0]
        if first in ids:
            return f"heading starts with task id {first!r}"
    stripped = prose.strip()
    if stripped.startswith("|") and stripped.endswith("|"):
        first = stripped.strip("|").split("|")[0].strip()
        first = link[1] if (link := _CELL_LINK.fullmatch(first)) else first
        if first in ids:
            return f"table row for task id {first!r}"
    if PENDING.search(prose):
        return "'待 human'"
    return None


def _markdown(listing: str) -> list[str]:
    return sorted(
        path
        for path in listing.split("\0")
        if path.lower().endswith(".md") and path.split("/", 1)[0] not in PRUNED_DIRS
    )


def _added_lines(root: Path, base: str, relative: str) -> set[int]:
    lines: set[int] = set()
    for line in _git(root, "diff", "-U0", "--relative", base, "--", relative).splitlines():
        if match := _HUNK.match(line):
            start = int(match[1])
            lines.update(range(start, start + int(match[2] or 1)))
    return lines


def _link_problem(root: Path, source: Path, target: str) -> str | None:
    if target.startswith("#"):
        return None
    parts = urlsplit(target)
    if len(parts.scheme) > 1:
        if parts.scheme in {"http", "https"} and not parts.netloc:
            return "malformed URL"
        return None
    relative = unquote(parts.path)
    if not relative:
        return None
    path = (root / relative.lstrip("/") if relative.startswith("/") else source.parent / relative).resolve()
    for name in PRUNED_DIRS:
        pruned = root / name
        if path == pruned or pruned in path.parents:
            return f"link into {name}/, which CLOSE prunes"
    return None if path.exists() else "dead link"


def _is_readme(relative: str) -> bool:
    return PurePosixPath(relative).name.lower() == "readme.md"


def _layout_problems(root: Path, relative: str) -> list[str]:
    """features/<feature>.md and exps/<feature>.md sit directly in their directory; an exp opens with the entry fields."""
    parts = PurePosixPath(relative).parts
    if parts[0] not in (FEATURES_DIR, EXPS_DIR):
        return []
    if len(parts) != 2:
        return [f"{relative}: put it directly in {parts[0]}/ as <feature>.md, without subdirectories"]
    if parts[0] == FEATURES_DIR:
        return []
    problems = []
    if not (root / FEATURES_DIR / parts[1]).is_file():
        problems.append(f"{relative}: no {FEATURES_DIR}/{parts[1]}; each exp document has a feature of the same name")
    found = set()
    for line in (root / relative).read_text(encoding="utf-8", errors="replace").splitlines():
        if _SECTION.match(line):
            break
        if field := _FIELD.match(line):
            found.add(field[1])
    if missing := [field for field in ENTRY_FIELDS if field not in found]:
        problems.append(f"{relative}: entry fields missing before the first ## section: {'、'.join(missing)}")
    return problems


def _exempt_lines(lines: list[str], ids: set[str], *, sections: bool) -> set[int]:
    """Line numbers where task ids are legitimate: a feature's task sections, or an exp's Experiment Log."""
    if sections:
        return {index + 1 for task_id in ids for start, end in _task_sections(lines, task_id)
                for index in range(start, end)}
    exempt, inside = set(), False
    for number, line in enumerate(lines, 1):
        if _SECTION.match(line):
            inside = bool(EXPERIMENT_LOG.match(line))
        elif inside and line.strip().startswith("|"):
            exempt.add(number)
    return exempt


def _task_table_problems(root: Path, added: set[int]) -> list[str]:
    """Rows this task added to an `| id | task |` table must have the template's column count."""
    problems = []
    task_table = in_table = False
    lines = (root / TASK_FILE).read_text(encoding="utf-8", errors="replace").splitlines()
    for number, line in enumerate(lines, 1):
        stripped = line.strip()
        if not (stripped.startswith("|") and stripped.endswith("|")):
            in_table = False
            continue
        cells = [cell.strip() for cell in stripped.strip("|").split("|")]
        if not in_table:
            in_table = True
            task_table = cells[0] == "id"
        if not task_table or number not in added or not stripped.strip("|-: "):
            continue
        if len(cells) != TASK_COLUMNS:
            problems.append(
                f"{TASK_FILE}:{number}: task table row has {len(cells)} cells; "
                f"the task-state template has {TASK_COLUMNS}"
            )
    return problems


def _check(root: Path, relative: str, added: set[int] | None, ids: set[str] | None,
           exempt: set[int] = frozenset()) -> list[str]:
    source = root / relative
    problems = []
    index = _is_readme(relative)
    fenced = False
    for number, line in enumerate(source.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if _FENCE.match(line):
            fenced = not fenced
            continue
        if fenced:
            continue
        prose = _CODE_SPAN.sub("", line)
        targets = _INLINE_LINK.findall(prose)
        if reference := _REFERENCE.match(prose):
            targets.append(reference[1])
        for target in targets:
            if reason := _link_problem(root, source, target):
                problems.append(f"{relative}:{number}: {reason}: {target}")
        if (added is None or number in added) and ALLOW not in line:
            if word := LEFTOVER.search(prose):
                problems.append(
                    f"{relative}:{number}: leftover {word[0]!r}; finish the line or mark it {ALLOW}"
                )
            if ids is not None and number not in exempt and (reason := _design_state(prose, ids)):
                problems.append(f"{relative}:{number}: {reason}; {DESIGN_STATE} or mark it {ALLOW}")
            if (index and _INDEX_LINE.match(prose) and _INLINE_LINK.search(prose)
                    and not _WORD.search(_INLINE_LINK.sub("", prose))):
                problems.append(
                    f"{relative}:{number}: link-only index line; add one sentence of current fact or mark it {ALLOW}"
                )
    return problems


def lint_changed(root: Path) -> list[str]:
    """Problems in the markdown changed since this task's init (HEAD without a task)."""
    root = root.resolve()
    config = _config(root)
    base = (config.get("lint") or {}).get("base") or "HEAD"
    plan_doc = config.get("plan_doc")
    ids = task_ids(root) if plan_doc else set()
    plan = (root / plan_doc).resolve() if plan_doc else None

    feature = plan is not None and feature_doc(root, plan)

    def design_ids(relative: str) -> set[str] | None:
        path = (root / relative).resolve()
        if plan and not feature and (path == plan or path.is_relative_to(plan.parent / SUB_EXP)):
            return None
        return ids

    def exempt(relative: str) -> set[int]:
        path = (root / relative).resolve()
        if not feature or path not in (plan, (root / EXPS_DIR / plan.name).resolve()):
            return set()
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return _exempt_lines(lines, ids, sections=path == plan)

    tracked = _markdown(_git(root, "diff", "--name-only", "-z", "--relative", "--diff-filter=d", base, "--"))
    untracked = _markdown(_git(root, "ls-files", "--others", "--exclude-standard", "-z"))
    ignored = _markdown(_git(root, "ls-files", "--others", "--ignored", "--exclude-standard", "-z",
                             "--", FEATURES_DIR, EXPS_DIR))
    problems = [f"{relative}: not tracked by git" for relative in untracked]
    problems += [f"{relative}: ignored by git; {FEATURES_DIR}/ and {EXPS_DIR}/ are tracked" for relative in ignored]
    for relative in tracked:
        problems += _check(root, relative, _added_lines(root, base, relative), design_ids(relative), exempt(relative))
    for relative in untracked:
        problems += _check(root, relative, None, design_ids(relative), exempt(relative))
    problems += [reason for relative in [*tracked, *untracked] for reason in _layout_problems(root, relative)]
    if (root / TASK_FILE).is_file() and _git(root, "diff", "--name-only", "--relative", base, "--", TASK_FILE).strip():
        problems += _task_table_problems(root, _added_lines(root, base, TASK_FILE))
    return problems
