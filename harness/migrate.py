"""Convert the 7-column task tables of task.md to the 4-column form, writing nothing until every row resolves."""
from __future__ import annotations

import hashlib
import re
import shutil
from pathlib import Path
from typing import Any

from harness import failures

from harness.errors import HarnessError
from harness.project import task_file
from harness.records import (
    _HEADING,
    _REVISION_LINE,
    _atomic_write,
    _cells,
    _separator,
    design_spans,
)
from harness.storage import atomic_write_json, harness_dir, read_json

MIGRATE_DIR = "migrate"
MANIFEST = "manifest.json"
PRIORITY = re.compile(r"(?<![A-Za-z0-9_])P\d+(?![\w.])")


def _blocks(lines: list[str]) -> list[tuple[int, int]]:
    """[start, end) of every run of table lines."""
    blocks, start = [], None
    for index, line in enumerate([*lines, ""]):
        if _cells(line) is not None:
            start = index if start is None else start
        elif start is not None:
            blocks.append((start, index))
            start = None
    return blocks


def _recover(root: Path) -> None:
    """Restore the files of a migration that stopped before its manifest was marked done."""
    for manifest in sorted((harness_dir(root) / MIGRATE_DIR).glob(f"*/{MANIFEST}")):
        data = read_json(manifest)
        if data.get("done"):
            continue
        for index, relative in enumerate(data["files"]):
            shutil.copyfile(manifest.parent / str(index), root / relative)


def _rewrite(text: str, mapping: dict[str, list[str]], where: str, errors: list[str]) -> str:
    def replace(match: re.Match[str]) -> str:
        ids = mapping.get(match.group(0), [])
        if len(ids) != 1:
            errors.append(f"{where}: `{match.group(0)}` matches {len(ids)} rows ({', '.join(ids) or 'none'}); "
                          "replace it with the task id it means")
            return match.group(0)
        return ids[0]

    return PRIORITY.sub(replace, text)


def _with_revision(lines: list[str], start: int, end: int, revision: str) -> list[str]:
    line = f"- rev：{revision}"
    heading = next((index for index in range(start, end) if _HEADING.match(lines[index])), None)
    if heading is None:
        return [*lines[:start], line, "", *lines[start:]]
    after = heading + 1
    if after >= len(lines):
        return [*lines, "", line]
    if lines[after].strip():
        return [*lines[:after], "", line, "", *lines[after:]]
    following = lines[after + 1] if after + 1 < len(lines) else ""
    insert = [line] if following.lstrip().startswith("- ") else [line, ""]
    return [*lines[:after + 1], *insert, *lines[after + 1:]]


def migrate_tasks(root: Path) -> dict[str, Any]:
    root = root.resolve()
    _recover(root)
    path = task_file(root)
    if not path.exists():
        raise HarnessError(f"{path} does not exist")
    source = path.read_text(encoding="utf-8")
    lines = source.splitlines()
    digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    errors: list[str] = []

    tables = []
    for start, end in _blocks(lines):
        header = _cells(lines[start]) or []
        body = [index for index in range(start + 1, end) if not _separator(_cells(lines[index]) or [])]
        legacy = len(header) == 7 and header[:2] == ["P", "id"]
        tables.append((start, end, header, body, legacy))
    if not any(table[4] for table in tables):
        return {"migrated": False, "reason": "task.md has no 7-column task table"}

    everywhere: dict[str, list[str]] = {}
    for _, _, _, body, legacy in tables:
        for index in body if legacy else []:
            cells = _cells(lines[index]) or []
            everywhere.setdefault(cells[0], []).append(cells[1])

    replaced: dict[int, list[str]] = {}
    counts: dict[str, int] = {}
    revisions: list[tuple[str, str, str]] = []
    for start, end, header, body, legacy in tables:
        if not legacy:
            if header and header[0] == "P":
                for index in body:
                    cells = _cells(lines[index]) or []
                    rest = [_rewrite(cell, everywhere, f"task.md:{index + 1}", errors) for cell in cells[1:]]
                    replaced[index] = ["| " + " | ".join([cells[0], *rest]) + " |"]
            continue
        rows = []
        local: dict[str, list[str]] = {}
        for index in body:
            cells = _cells(lines[index]) or []
            if len(cells) != 7 or not re.fullmatch(r"P\d+", cells[0]):
                errors.append(f"task.md:{index + 1}: a task row needs 7 cells and a P<number> priority")
                continue
            if not re.fullmatch(r"\d*", cells[6]):
                errors.append(f"task.md:{index + 1}: failure cell `{cells[6]}` is not a number")
                continue
            rows.append((index, cells))
            local.setdefault(cells[0], []).append(cells[1])
        new_rows = []
        for index, (priority, task_id, revision, task, check, status, failed) in sorted(
            rows, key=lambda row: int(row[1][0][1:])
        ):
            check = _rewrite(check, local, f"task.md:{index + 1}", errors)
            new_rows.append(f"| {task_id} | {task} | {check} | {status} |")
            if int(failed or 0):
                counts[task_id] = int(failed)
            if revision != "—":
                revisions.append((task_id, revision, lines[index]))
        replaced[start] = [
            "| " + " | ".join([header[1], header[3], header[4], header[5]]) + " |",
            "|---|---|---|---|",
            *new_rows,
        ]
        for index in range(start + 1, end):
            replaced[index] = []

    sections: dict[Path, list[tuple[int, int, str]]] = {}
    for task_id, revision, row in revisions:
        spans = design_spans(root, task_id, row)
        if not spans:
            errors.append(f"task {task_id} binds {revision} but its row links no design section to hold `- rev：`")
            continue
        target, start, end = spans[0]
        sections.setdefault(target, []).append((start, end, revision))
    edits: dict[Path, list[str]] = {}
    for target, items in sections.items():
        content = target.read_text(encoding="utf-8").splitlines()
        # Bottom-up, so an insertion never shifts a section still to be edited.
        for start, end, revision in sorted(items, reverse=True):
            existing = [index for index in range(start, end) if _REVISION_LINE.match(content[index])]
            for index in existing:
                content[index] = f"- rev：{revision}"
            if not existing:
                content = _with_revision(content, start, end, revision)
        edits[target] = content
    if errors:
        raise HarnessError("migrate-tasks wrote nothing:\n" + "\n".join(errors))

    output = []
    for index, line in enumerate(lines):
        output.extend(replaced.get(index, [line]))
    writes = {path: "\n".join(output) + "\n"}
    writes.update({target: "\n".join(content) + "\n" for target, content in edits.items()})

    backup = harness_dir(root) / MIGRATE_DIR / digest
    backup.mkdir(parents=True, exist_ok=True)
    files = sorted(writes)
    for index, target in enumerate(files):
        shutil.copyfile(target, backup / str(index))
    manifest = {"files": [target.relative_to(root).as_posix() for target in files], "done": False}
    atomic_write_json(backup / MANIFEST, manifest)
    for target in files:
        _atomic_write(target, writes[target])
    failures.import_counts(root, digest, counts)
    atomic_write_json(backup / MANIFEST, {**manifest, "done": True})
    return {
        "migrated": True,
        "tasks": sum(len(body) for _, _, _, body, legacy in tables if legacy),
        "revisions": len(revisions),
        "failures": counts,
        "files": manifest["files"],
        "backup": backup.relative_to(root).as_posix(),
    }
