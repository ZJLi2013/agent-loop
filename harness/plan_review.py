from __future__ import annotations

from pathlib import Path
from typing import Any

from harness.errors import HarnessError
from harness.fingerprint import workspace_fingerprint
from harness.journal import append_journal, new_run_id, prune_artifacts
from harness.project import render_prompt, review_checklist, task_file
from harness.records import open_task_ids, task_digest, task_row
from harness.review import load_reviewer
from harness.runner import execute_process
from harness.storage import (
    atomic_write_json,
    harness_dir,
    read_json,
    state_lock,
    utc_now,
)

PLAN_REVIEW_DIR = "plan-review"
TASK_RECORDS = "tasks"
VERDICTS = ("accept", "revise")
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
    return read_json(path)


def review_status(root: Path, task_id: str) -> tuple[str, str | None]:
    digest = task_digest(root, task_id)
    if digest is None:
        return "missing", None
    record = task_record(root, task_id)
    if any(item["digest"] == digest for item in record["approvals"]):
        return "approved", digest
    reviews = record["reviews"]
    if any(item["digest"] == digest for item in reviews):
        return "reviewed", digest
    if reviews and reviews[-1]["verdict"] == "revise":
        decided = [item["at"] for item in record["approvals"] + record["again"]]
        if not any(at >= reviews[-1]["at"] for at in decided):
            return "needs_human", digest
    return "needs_review", digest


def admitted(root: Path, task_id: str, digest: str) -> bool:
    record = task_record(root, task_id)
    return any(item["digest"] == digest for item in record["reviews"] + record["approvals"])


def plan_review_ready(
    root: Path, task_id: str, *, review: str | None = None
) -> tuple[bool, str | None]:
    status, _ = review_status(root, task_id)
    if status == "approved":
        if review == "unreviewed":
            raise HarnessError(
                f"task {task_id} rests on a human approval, which needs "
                "Plan Review: approved, not unreviewed self-approval"
            )
        return True, None
    if status == "reviewed":
        return True, None
    if status == "missing":
        return False, f"task {task_id} is missing from the task list"
    if status == "needs_human":
        return False, (
            f"the reviewer sent task {task_id} back; ask the human to choose: "
            f'plan-review --approve {task_id} --reason "<human words>" or '
            f'plan-review --again {task_id} --reason "<human words>"'
        )
    return False, f"task {task_id} has no independent review of its current design"


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
        return None, "tasks must map each requested task id to its verdict"
    verdicts = {}
    for task_id in tasks:
        entry = entries.get(task_id)
        if not isinstance(entry, dict):
            return None, f"report has no verdict for task {task_id}"
        verdict, findings = entry.get("verdict"), entry.get("findings")
        if verdict not in VERDICTS:
            return None, f"task {task_id}: verdict must be one of {', '.join(VERDICTS)}"
        if not isinstance(findings, list) or not all(
            isinstance(item, str) and item.strip() for item in findings
        ):
            return None, f"task {task_id}: findings must be a list of non-empty strings"
        if verdict == "revise" and not findings:
            return None, f"task {task_id}: revise requires at least one finding"
        verdicts[task_id] = {
            "verdict": verdict,
            "findings": [item.strip() for item in findings],
        }
    return {"summary": summary.strip(), "tasks": verdicts}, None


def _task_lines(root: Path, tasks: list[str]) -> str:
    lines = []
    for task_id in tasks:
        cells = task_row(root, task_id) or []
        title, check = (cells[3], cells[4]) if len(cells) > 4 else ("", "")
        lines.append(f"- {task_id}：{title}。验收：{check}")
    return "\n".join(lines)


def _append(root: Path, task_id: str, key: str, entry: dict[str, Any]) -> None:
    record = task_record(root, task_id)
    record[key].append(entry)
    atomic_write_json(_record_path(root, task_id), record)


def record_task_review(
    root: Path, task_id: str, *, verdict: str, findings: list[str], summary: str,
    source: str, run_id: str | None,
) -> None:
    digest = task_digest(root, task_id)
    if digest is None:
        raise HarnessError(f"task {task_id} is missing from the task list")
    _append(root, task_id, "reviews", {
        "digest": digest,
        "verdict": verdict,
        "findings": findings,
        "summary": summary,
        "source": source,
        "run_id": run_id,
        "at": utc_now(),
    })


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
        statuses = {task_id: review_status(root, task_id)[0] for task_id in open_task_ids(root)}
        pending = [task_id for task_id, status in statuses.items() if status == "needs_review"]
        waiting = [task_id for task_id, status in statuses.items() if status == "needs_human"]
        if not pending:
            return {"summary": None, "tasks": {}, "waiting": waiting}

        review_dir = _review_dir(root)
        review_dir.mkdir(parents=True, exist_ok=True)
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
            raise HarnessError(f"plan review failed: {error}")
        for task_id, entry in report["tasks"].items():
            record_task_review(
                root, task_id, **entry, summary=report["summary"],
                source="plan_review", run_id=run_id,
            )
        return {"summary": report["summary"], "tasks": report["tasks"], "waiting": waiting}


def _human_decision(root: Path, task_id: str, reason: str, *, key: str, kind: str) -> dict[str, Any]:
    root = root.resolve()
    if not reason.strip():
        raise HarnessError(f"--{key} requires --reason quoting the human decision")
    with state_lock(root):
        status, digest = review_status(root, task_id)
        if status == "missing":
            raise HarnessError(f"task {task_id} is missing from the task list")
        if not task_record(root, task_id)["reviews"]:
            raise HarnessError(f"task {task_id} has never been reviewed; run plan-review first")
        if key == "again" and status != "needs_human":
            raise HarnessError(f"task {task_id} does not need a human decision ({status})")
        entry = {"digest": digest, "reason": reason.strip(), "at": utc_now()}
        _append(root, task_id, "approvals" if key == "approve" else "again", entry)
        run_id = new_run_id()
        run_dir = harness_dir(root) / "artifacts" / run_id
        run_dir.mkdir(parents=True)
        result = {
            "version": 1,
            "run_id": run_id,
            "task_id": task_id,
            "kind": kind,
            "argv": [],
            "started_at": entry["at"],
            "duration_seconds": 0.0,
            "timed_out": False,
            "exit_code": 0,
            "outcome": "pass",
            **entry,
        }
        atomic_write_json(run_dir / "result.json", result)
        append_journal(root, result, DEFAULT_MAX_JOURNAL_ENTRIES)
        prune_artifacts(root, DEFAULT_MAX_ARTIFACTS)
    return {"task_id": task_id, key: entry}


def approve_task(root: Path, task_id: str, *, reason: str) -> dict[str, Any]:
    return _human_decision(root, task_id, reason, key="approve", kind="plan_review_approval")


def again_task(root: Path, task_id: str, *, reason: str) -> dict[str, Any]:
    return _human_decision(root, task_id, reason, key="again", kind="plan_review_again")
