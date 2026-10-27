from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from harness.errors import HarnessError
from harness.findings import normalize_findings
from harness.fingerprint import workspace_fingerprint
from harness.journal import append_journal, new_run_id, prune_artifacts
from harness.project import render_prompt, review_checklist, task_file
from harness.records import open_task_ids, task_row
from harness.review import load_reviewer
from harness.runner import execute_process
from harness.storage import (
    atomic_write_json,
    harness_dir,
    pid_alive,
    read_json,
    state_lock,
    utc_now,
)

PLAN_REVIEW_DIR = "plan-review"
RUNNING_FILE = "running.json"
TASK_RECORDS = "tasks"
RESPONSES = ("applied", "skipped", "reject")
DEFAULT_MAX_OUTPUT_BYTES = 1_048_576
DEFAULT_MAX_ARTIFACTS = 20
DEFAULT_MAX_JOURNAL_ENTRIES = 1000


def _plan_path(root: Path, plan_doc: str) -> tuple[Path, str]:
    root = root.resolve()
    path = (root / plan_doc).resolve()
    try:
        relative = path.relative_to(root).as_posix()
    except ValueError as exc:
        raise HarnessError("plan document must be inside the project root") from exc
    if not path.is_file():
        raise HarnessError(f"plan document does not exist: {relative}")
    return path, relative


def _checklist_line(root: Path) -> str:
    path = review_checklist(root)
    if path is None:
        return ""
    return f"- repo 检查表：`{path.resolve().relative_to(root.resolve()).as_posix()}`\n"


def _review_dir(root: Path) -> Path:
    return harness_dir(root) / PLAN_REVIEW_DIR


def _record_path(root: Path, task_id: str) -> Path:
    return _review_dir(root) / TASK_RECORDS / f"{task_id}.json"


def task_record(root: Path, task_id: str) -> dict[str, Any]:
    path = _record_path(root, task_id)
    if not path.exists():
        return {"task_id": task_id, "reviews": [], "approvals": [], "again": []}
    record = read_json(path)
    # Records written before the must / suggest protocol hold plain-string findings.
    for review in record["reviews"]:
        review.setdefault("responses", {})
        review.setdefault("dropped", 0)
        review["findings"] = [
            {"level": "suggest", "claim": item, "consequence": "", "evidence": "", "change": "", "human": False}
            if isinstance(item, str)
            else item
            for item in review["findings"]
        ]
    return record


def _write(root: Path, record: dict[str, Any]) -> None:
    atomic_write_json(_record_path(root, record["task_id"]), record)


def review_status(root: Path, task_id: str, plan_doc: str) -> str:
    if task_row(root, task_id) is None:
        return "missing"
    _, plan = _plan_path(root, plan_doc)
    record = task_record(root, task_id)
    reviews = record["reviews"]
    # Task ids restart across Goals; reviews recorded before plan_doc existed count for this plan.
    if not reviews or reviews[-1].get("plan_doc", plan) != plan:
        return "not_reviewed"
    if any(item["at"] >= reviews[-1]["at"] for item in record["again"]):
        return "needs_review"
    return "reviewed"


def plan_review_ready(
    root: Path, task_id: str, *, plan_doc: str, review: str | None = None
) -> tuple[bool, str | None]:
    status = review_status(root, task_id, plan_doc)
    if status == "missing":
        return False, f"task {task_id} is missing from the task list"
    if status in {"not_reviewed", "needs_review"}:
        return False, f"task {task_id} has no independent review"
    record = task_record(root, task_id)
    last = record["reviews"][-1]
    findings = last["findings"]
    open_items = [
        str(index)
        for index, item in enumerate(findings, start=1)
        if item["level"] == "must" and str(index) not in last["responses"]
    ]
    if open_items:
        return False, (
            f"answer the reviewer's must items {', '.join(open_items)} of task {task_id}: "
            f"plan-review --respond {task_id} --item N=applied (or N=reject --reason \"<fact>\")"
        )
    if any(item["human"] for item in findings):
        if not any(item["at"] >= last["at"] for item in record["approvals"]):
            return False, (
                f"task {task_id} has a reviewer item for the human to decide: "
                f'plan-review --approve {task_id} --reason "<human words>"'
            )
        if review == "unreviewed":
            raise HarnessError(
                f"task {task_id} rests on a human decision, which needs "
                "Plan Review: approved, not unreviewed self-approval"
            )
    return True, None


def _read_report(
    path: Path, tasks: list[str]
) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "plan reviewer did not write report"
    try:
        value = read_json(path)
    except HarnessError as exc:
        return None, str(exc)
    summary = value.get("summary")
    entries = value.get("tasks")
    if not isinstance(summary, str) or not summary.strip():
        return None, "summary is required"
    if not isinstance(entries, dict):
        return None, "tasks must map each requested task id to its findings"
    reviewed = {}
    for task_id in tasks:
        entry = entries.get(task_id)
        if not isinstance(entry, dict):
            return None, f"report has no entry for task {task_id}"
        findings, dropped, error = normalize_findings(entry.get("findings", []))
        if error:
            return None, f"task {task_id}: {error}"
        reviewed[task_id] = {"findings": findings, "dropped": dropped}
    return {"summary": summary.strip(), "tasks": reviewed}, None


def _task_lines(root: Path, tasks: list[str]) -> str:
    lines = []
    for task_id in tasks:
        cells = task_row(root, task_id) or []
        title, check = (cells[3], cells[4]) if len(cells) > 4 else ("", "")
        lines.append(f"- {task_id}：{title}。验收：{check}")
    return "\n".join(lines)


def record_task_review(
    root: Path,
    task_id: str,
    *,
    findings: list[dict[str, Any]],
    dropped: int,
    summary: str,
    source: str,
    run_id: str | None,
    plan_doc: str,
) -> None:
    record = task_record(root, task_id)
    record["reviews"].append({
        "plan_doc": _plan_path(root, plan_doc)[1],
        "findings": findings,
        "dropped": dropped,
        "summary": summary,
        "source": source,
        "run_id": run_id,
        "responses": {},
        "at": utc_now(),
    })
    _write(root, record)


def run_plan_review(
    root: Path,
    *,
    plan_doc: str,
    reviewer_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    reviewer = reviewer_config or load_reviewer(root)
    if not reviewer:
        raise HarnessError("no reviewer configured")
    _, relative = _plan_path(root, plan_doc)

    with state_lock(root):
        pending = [
            task_id
            for task_id in open_task_ids(root)
            if review_status(root, task_id, relative) in {"not_reviewed", "needs_review"}
        ]
        if not pending:
            return {"summary": None, "tasks": {}}

        review_dir = _review_dir(root)
        review_dir.mkdir(parents=True, exist_ok=True)
        running = review_dir / RUNNING_FILE
        holder = read_json(running) if running.exists() else None
        if holder and pid_alive(int(holder["pid"])):
            raise HarnessError(
                f"plan review run {holder.get('run_id')} is in progress "
                f"(pid {holder.get('pid')}); wait for it to finish"
            )
        report_path = review_dir / "report.json"
        prompt_path = harness_dir(root) / "review" / "prompt.md"
        report_path.unlink(missing_ok=True)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(
            render_prompt(
                "plan_review.md",
                plan_doc=relative,
                task_doc=task_file(root).resolve().relative_to(root).as_posix(),
                tasks=_task_lines(root, pending),
                checklist=_checklist_line(root),
                report_file=report_path.resolve().relative_to(root).as_posix(),
            ),
            encoding="utf-8",
        )

        before = workspace_fingerprint(root)
        run_id = new_run_id()
        run_dir = harness_dir(root) / "artifacts" / run_id
        run_dir.mkdir(parents=True)
        atomic_write_json(running, {"run_id": run_id, "pid": os.getpid(), "at": utc_now()})

    try:
        execution = execute_process(
            root,
            list(reviewer["argv"]),
            timeout_seconds=float(reviewer["timeout_seconds"]),
            run_dir=run_dir,
            max_output_bytes=DEFAULT_MAX_OUTPUT_BYTES,
            is_paused=lambda: False,
        )
        report, error = (
            _read_report(report_path, pending)
            if execution["outcome"] == "pass"
            else (None, f"plan reviewer {execution['outcome']}")
        )
        if before != workspace_fingerprint(root):
            report, error = None, "plan reviewer modified the workspace"
    except BaseException:
        running.unlink(missing_ok=True)
        raise

    with state_lock(root):
        result = {
            "version": 1,
            "run_id": run_id,
            "task_id": "plan",
            "kind": "plan_review",
            "argv": list(reviewer["argv"]),
            "plan_doc": relative,
            "tasks": pending,
            **execution,
            "report": report,
            "error": error,
        }
        atomic_write_json(run_dir / "result.json", result)
        append_journal(root, result, DEFAULT_MAX_JOURNAL_ENTRIES)
        prune_artifacts(root, DEFAULT_MAX_ARTIFACTS)
        if error or report is None:
            running.unlink(missing_ok=True)
            raise HarnessError(f"plan review failed: {error}")
        for task_id, entry in report["tasks"].items():
            record_task_review(
                root, task_id, **entry, summary=report["summary"],
                source="plan_review", run_id=run_id, plan_doc=relative,
            )
        running.unlink(missing_ok=True)
        return report


def _journal_decision(root: Path, task_id: str, kind: str, entry: dict[str, Any]) -> None:
    run_id = new_run_id()
    run_dir = harness_dir(root) / "artifacts" / run_id
    run_dir.mkdir(parents=True)
    result = {
        "version": 1,
        "run_id": run_id,
        "task_id": task_id,
        "kind": kind,
        "argv": [],
        "started_at": utc_now(),
        "duration_seconds": 0.0,
        "timed_out": False,
        "exit_code": 0,
        "outcome": "pass",
        **entry,
    }
    atomic_write_json(run_dir / "result.json", result)
    append_journal(root, result, DEFAULT_MAX_JOURNAL_ENTRIES)
    prune_artifacts(root, DEFAULT_MAX_ARTIFACTS)


def _reviewed_record(root: Path, task_id: str) -> dict[str, Any]:
    if task_row(root, task_id) is None:
        raise HarnessError(f"task {task_id} is missing from the task list")
    record = task_record(root, task_id)
    if not record["reviews"]:
        raise HarnessError(f"task {task_id} has never been reviewed; run plan-review first")
    return record


def _human(root: Path, task_id: str, reason: str, *, key: str, kind: str) -> dict[str, Any]:
    root = root.resolve()
    if not reason.strip():
        raise HarnessError(f"--{key} requires --reason quoting the human decision")
    with state_lock(root):
        record = _reviewed_record(root, task_id)
        entry = {"reason": reason.strip(), "at": utc_now()}
        record["approvals" if key == "approve" else "again"].append(entry)
        _write(root, record)
        _journal_decision(root, task_id, kind, entry)
    return {"task_id": task_id, key: entry}


def approve_task(root: Path, task_id: str, *, reason: str) -> dict[str, Any]:
    return _human(root, task_id, reason, key="approve", kind="plan_review_approval")


def again_task(root: Path, task_id: str, *, reason: str) -> dict[str, Any]:
    return _human(root, task_id, reason, key="again", kind="plan_review_again")


def respond_task(
    root: Path, task_id: str, *, items: list[str], reason: str | None = None
) -> dict[str, Any]:
    root = root.resolve()
    with state_lock(root):
        record = _reviewed_record(root, task_id)
        last = record["reviews"][-1]
        for item in items:
            index, _, status = item.partition("=")
            if not index.isdigit() or not 1 <= int(index) <= len(last["findings"]):
                raise HarnessError(f"task {task_id} has no reviewer item {index}")
            if status not in RESPONSES:
                raise HarnessError(f"response must be one of {', '.join(RESPONSES)}")
            finding = last["findings"][int(index) - 1]
            if finding["level"] == "must" and status == "skipped":
                raise HarnessError(f"must item {index} is applied or rejected, not skipped")
            if status == "reject" and not (reason or "").strip():
                raise HarnessError("reject requires --reason naming the fact the item gets wrong")
            if index in last["responses"]:
                raise HarnessError(f"item {index} of task {task_id} is already answered")
            last["responses"][index] = {
                "status": status,
                "reason": (reason or "").strip() or None,
                "at": utc_now(),
            }
        _write(root, record)
        _journal_decision(root, task_id, "plan_review_response", {"items": items, "reason": reason})
    return {"task_id": task_id, "responses": last["responses"]}
