from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from harness.errors import HarnessError
from harness.fingerprint import workspace_fingerprint
from harness.journal import append_journal, new_run_id, prune_artifacts
from harness.plan import plan_metadata
from harness.project import render_prompt, review_checklist, task_file
from harness.records import open_task_ids
from harness.review import load_reviewer
from harness.runner import execute_process
from harness.storage import (
    JOURNAL_FILE,
    atomic_write_json,
    harness_dir,
    read_json,
    state_lock,
    utc_now,
)

PLAN_REVIEW_DIR = "plan-review"
VERDICTS = ("accept", "revise")
BRAKE_THRESHOLD = 3
BRAKE_PREFIX = "plan review brake"
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


def _review_key(plan_doc: str, revision: int) -> str:
    digest = hashlib.sha256(plan_doc.encode()).hexdigest()[:12]
    return f"{digest}-r{revision}"


def _review_dir(root: Path) -> Path:
    return harness_dir(root) / PLAN_REVIEW_DIR


def _read_report(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return None, "plan reviewer did not write report"
    try:
        value = read_json(path)
    except HarnessError as exc:
        return None, str(exc)
    verdict = value.get("verdict")
    summary = value.get("summary")
    findings = value.get("findings")
    if verdict not in VERDICTS:
        return None, f"verdict must be one of {', '.join(VERDICTS)}"
    if not isinstance(summary, str) or not summary.strip():
        return None, "summary is required"
    if not isinstance(findings, list) or not all(
        isinstance(item, str) and item.strip() for item in findings
    ):
        return None, "findings must be a list of non-empty strings"
    if verdict == "revise" and not findings:
        return None, "revise requires at least one finding"
    return {
        "verdict": verdict,
        "summary": summary.strip(),
        "findings": [item.strip() for item in findings],
    }, None


def plan_review_record(
    root: Path, plan_doc: str, revision: int
) -> dict[str, Any] | None:
    _, relative = _plan_path(root, plan_doc)
    path = _review_dir(root) / f"{_review_key(relative, revision)}.json"
    if not path.exists():
        return None
    value = read_json(path)
    if value.get("plan_doc") != relative or value.get("revision") != revision:
        raise HarnessError(f"invalid plan review record: {path}")
    return value


def plan_review_ready(
    root: Path,
    plan_doc: str,
    revision: int,
    *,
    review: str | None = None,
    task_id: str | None = None,
) -> tuple[bool, str | None]:
    record = plan_review_record(root, plan_doc, revision)
    if not record:
        return False, f"Plan Revision {revision} has no independent review"
    if record.get("error"):
        return False, f"Plan Revision {revision} review failed: {record['error']}"
    if record.get("verdict") == "waived":
        if review == "unreviewed":
            raise HarnessError(
                f"r{revision} review was waived; waivers need human approval, "
                "not unreviewed self-approval"
            )
        if task_id is not None and task_id not in record.get("tasks", []):
            raise HarnessError(
                f"task {task_id} is not covered by the r{revision} waiver; "
                "run the plan review"
            )
    return True, None


def _human_reset(record: dict[str, Any]) -> bool:
    return record.get("verdict") == "waived" or "brake_ack" in record


def _brake_warnings(
    records: list[dict[str, Any]], journal: list[dict[str, Any]]
) -> list[str]:
    records = sorted(records, key=lambda record: record["revision"])
    warnings = []
    streak = []
    for record in reversed(records):
        if record.get("verdict") == "accept" or _human_reset(record):
            break
        if record.get("verdict") == "revise":
            streak.append(record["revision"])
    if len(streak) >= BRAKE_THRESHOLD:
        warnings.append(
            f"plan review returned revise {len(streak)} times in a row "
            f"(r{streak[-1]}–r{streak[0]}); check that this gate fits the task's "
            "cost before revising again"
        )
    experiments = [
        entry["started_at"]
        for entry in journal
        if entry.get("kind") in ("exec", "verify")
    ]
    resets = [record["at"] for record in records if _human_reset(record)]
    # A truncated journal makes the oldest entry too recent: it undercounts, never overcounts.
    base = max(
        [*experiments, *resets],
        default=min((entry["started_at"] for entry in journal), default=None),
    )
    since = [r["revision"] for r in records if base is not None and r["at"] > base]
    if len(since) >= BRAKE_THRESHOLD:
        warnings.append(
            f"{len(since)} plan revisions reviewed since the last exec/verify run "
            f"(r{since[0]}–r{since[-1]}); no new experiment evidence"
        )
    return warnings


def _plan_records(root: Path, relative: str) -> list[dict[str, Any]]:
    prefix = _review_key(relative, 0).removesuffix("-r0")
    return [
        record
        for path in _review_dir(root).glob(f"{prefix}-r*.json")
        if (record := read_json(path)).get("plan_doc") == relative
    ]


def review_brake(root: Path, plan_doc: str) -> list[str]:
    _, relative = _plan_path(root, plan_doc)
    records = _plan_records(root, relative)
    path = harness_dir(root) / JOURNAL_FILE
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    journal = [json.loads(line) for line in lines if line.strip()]
    return _brake_warnings(records, journal)


def run_plan_review(
    root: Path,
    *,
    plan_doc: str,
    reviewer_config: dict[str, Any] | None = None,
    ack_reason: str | None = None,
) -> dict[str, Any]:
    root = root.resolve()
    if ack_reason is not None and not ack_reason.strip():
        raise HarnessError("--continue requires --reason quoting the human decision")
    reviewer = reviewer_config or load_reviewer(root)
    if not reviewer:
        raise HarnessError("no reviewer configured")
    _, relative = _plan_path(root, plan_doc)
    revision, _ = plan_metadata(root, relative)
    if revision is None:
        raise HarnessError("plan document must define Plan Revision")

    with state_lock(root):
        existing = plan_review_record(root, relative, revision)
        if existing:
            if existing.get("error"):
                raise HarnessError(
                    f"plan review r{revision} is incomplete: {existing['error']}"
                )
            return {**existing, "warnings": review_brake(root, relative)}

        brake = review_brake(root, relative)
        if brake and ack_reason is None:
            raise HarnessError(
                f"{BRAKE_PREFIX}: {'; '.join(brake)}.\n"
                'Ask the human to choose: revise again (plan-review --continue --reason "<human words>"),\n'
                "approve the last reviewed revision unchanged, approve with notes "
                '(plan-review --waive --reason "<human words>";\n'
                "low-cost tasks whose design was already reviewed only), "
                "or stop (goal-review --decision stop)."
            )
        if ack_reason is not None and not brake:
            raise HarnessError("no plan review brake is active")

        review_dir = _review_dir(root)
        review_dir.mkdir(parents=True, exist_ok=True)
        key = _review_key(relative, revision)
        report_path = review_dir / "report.json"
        prompt_path = harness_dir(root) / "review" / "prompt.md"
        record_path = review_dir / f"{key}.json"
        report_path.unlink(missing_ok=True)
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text(
            render_prompt(
                "plan_review.md",
                plan_doc=relative,
                task_doc=task_file(root).resolve().relative_to(root).as_posix(),
                revision=revision,
                checklist=_checklist_line(root),
                report_file=report_path.resolve().relative_to(root).as_posix(),
            ),
            encoding="utf-8",
        )

        tasks = open_task_ids(root, revision)
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
        after = workspace_fingerprint(root)
        report, error = (
            _read_report(report_path)
            if execution["outcome"] == "pass"
            else (None, f"plan reviewer {execution['outcome']}")
        )
        if before != after:
            report = None
            error = "plan reviewer modified the workspace"

        record: dict[str, Any] = {
            "version": 1,
            "plan_doc": relative,
            "revision": revision,
            "run_id": run_id,
            "verdict": None,
            "summary": None,
            "findings": [],
            "error": error,
            "tasks": tasks,
            "at": utc_now(),
        }
        if ack_reason is not None:
            record["brake_ack"] = {"reason": ack_reason.strip(), "warnings": brake}
        if report:
            record.update(report)
        result = {
            "version": 1,
            "run_id": run_id,
            "task_id": f"plan:r{revision}",
            "kind": "plan_review",
            "argv": list(reviewer["argv"]),
            "plan_doc": relative,
            "revision": revision,
            **execution,
            "review": record,
        }
        atomic_write_json(record_path, record)
        atomic_write_json(run_dir / "result.json", result)
        append_journal(root, result, DEFAULT_MAX_JOURNAL_ENTRIES)
        prune_artifacts(root, DEFAULT_MAX_ARTIFACTS)
        if error:
            raise HarnessError(f"plan review r{revision} failed: {error}")
        return {**record, "warnings": review_brake(root, relative)}


def waive_plan_review(root: Path, *, plan_doc: str, reason: str) -> dict[str, Any]:
    root = root.resolve()
    if not reason.strip():
        raise HarnessError("--waive requires --reason quoting the human decision")
    _, relative = _plan_path(root, plan_doc)
    revision, _ = plan_metadata(root, relative)
    if revision is None:
        raise HarnessError("plan document must define Plan Revision")

    with state_lock(root):
        existing = plan_review_record(root, relative, revision)
        if existing and not existing.get("error"):
            raise HarnessError(
                f"r{revision} already has a plan review ({existing['verdict']}); "
                "approve it directly"
            )
        reviewed = [
            record
            for record in _plan_records(root, relative)
            if record["revision"] < revision and record.get("verdict") in VERDICTS
        ]
        covered = {task for record in reviewed for task in record.get("tasks", [])}
        tasks = open_task_ids(root, revision)
        missing = [task for task in tasks if task not in covered]
        if missing or not tasks:
            raise HarnessError(
                f"r{revision} proposes {', '.join(missing) or 'no open task'}, "
                "which no earlier plan review covered; run the plan review"
            )

        waived_from = max(record["revision"] for record in reviewed)
        now = utc_now()
        record = {
            "version": 1,
            "plan_doc": relative,
            "revision": revision,
            "run_id": None,
            "verdict": "waived",
            "summary": f"human waived plan review after r{waived_from}",
            "findings": [],
            "error": None,
            "tasks": tasks,
            "waived_from": waived_from,
            "reason": reason.strip(),
            "at": now,
        }
        run_id = new_run_id()
        run_dir = harness_dir(root) / "artifacts" / run_id
        run_dir.mkdir(parents=True)
        result = {
            "version": 1,
            "run_id": run_id,
            "task_id": f"plan:r{revision}",
            "kind": "plan_review_waiver",
            "argv": [],
            "started_at": now,
            "duration_seconds": 0.0,
            "timed_out": False,
            "exit_code": 0,
            "outcome": "pass",
            "plan_doc": relative,
            "revision": revision,
            "reason": record["reason"],
            "waived_from": waived_from,
        }
        record_path = _review_dir(root) / f"{_review_key(relative, revision)}.json"
        atomic_write_json(record_path, record)
        atomic_write_json(run_dir / "result.json", result)
        append_journal(root, result, DEFAULT_MAX_JOURNAL_ENTRIES)
        prune_artifacts(root, DEFAULT_MAX_ARTIFACTS)
    return {**record, "warnings": review_brake(root, relative)}
