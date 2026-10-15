from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from harness.errors import HarnessError
from harness.findings import describe, normalize_findings
from harness.fingerprint import workspace_fingerprint
from harness.journal import append_journal, new_run_id, prune_artifacts
from harness.plan import pause_request
from harness.project import (
    memory_dir,
    render_prompt,
    review_checklist,
    runtime_dir,
    task_file,
)
from harness.protocol import Phase
from harness.records import CLOSED_MARKERS, active_task_status, close_task
from harness.runner import execute_process
from harness.storage import (
    HARNESS_DIR,
    STATE_FILE,
    atomic_write_json,
    harness_dir,
    load_runtime,
    read_json,
    state_lock,
    utc_now,
)

REVIEWER_FILE = "reviewer.json"
REVIEW_DIR = "review"
DECISIONS = ("continue", "ask_human", "stop")
MAX_REVIEWS = 2
DEFAULT_REVIEW_TIMEOUT_SECONDS = 1800.0

def load_reviewer(root: Path) -> dict[str, Any] | None:
    path = runtime_dir(root) / REVIEWER_FILE
    if not path.exists():
        return None
    value = read_json(path)
    argv = value.get("argv")
    if not isinstance(argv, list) or not argv or not all(
        isinstance(arg, str) and arg for arg in argv
    ):
        raise HarnessError(f"{path} must define argv as a non-empty list of strings")
    timeout = float(value.get("timeout_seconds", DEFAULT_REVIEW_TIMEOUT_SECONDS))
    if timeout <= 0:
        raise HarnessError(f"{path} timeout_seconds must be positive")
    return {"argv": argv, "timeout_seconds": timeout}


def _review_dir(root: Path) -> Path:
    return harness_dir(root) / REVIEW_DIR


def _relative(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _prompt(
    root: Path,
    config: dict[str, Any],
    state: dict[str, Any],
    previous: dict[str, Any],
    objection: str | None,
) -> str:
    evidence = f"{HARNESS_DIR}/artifacts/{state['last_run_id']}"
    inputs = []
    if config.get("plan_doc"):
        inputs.append(f"- plan document：`{config['plan_doc']}`")
    inputs.append(f"- task 列表：`{_relative(root, task_file(root))}`")
    inputs.append(f"- 验证输出：`{evidence}/stdout.log`、`{evidence}/stderr.log`")
    inputs.append(f"- 执行记录：`{HARNESS_DIR}/runs.jsonl`")
    index = memory_dir(root) / "INDEX.md"
    if index.exists():
        inputs.append(f"- 项目记忆索引：`{_relative(root, index)}`")
    checklist = review_checklist(root)
    if checklist is not None:
        inputs.append(f"- repo 检查表：`{_relative(root, checklist)}`")
    extra = ""
    if objection:
        decision = {key: previous.get(key) for key in ("decision", "next_task", "why")}
        extra = (
            "\n## worker 的事实异议\n\n"
            f"上一次决策：`{json.dumps(decision, ensure_ascii=False)}`\n\n"
            f"{objection}\n\n核实后改正或维持；仍有分歧就选 `ask_human`。\n"
        )
    elif previous.get("error"):
        extra = f"\n## 上一次 review 无效\n\n{previous['error']}\n\n补齐后再写决策。\n"
    from harness.plan_review import task_record

    reviews = task_record(root, str(state["task_id"]))["reviews"]
    if reviews and reviews[-1]["findings"]:
        last = reviews[-1]
        lines = [
            f"{index}. [{item['level']}] {item['claim']} → "
            + json.dumps(last["responses"].get(str(index), {"status": "skipped"}), ensure_ascii=False)
            for index, item in enumerate(last["findings"], start=1)
        ]
        extra += "\n## 开工前的审查意见与 executor 回应\n\n" + "\n".join(lines) + "\n"
    return render_prompt(
        "task_review.md",
        task_id=state["task_id"],
        inputs="\n".join(inputs),
        extra=extra,
        decision_file=f"{HARNESS_DIR}/{REVIEW_DIR}/decision.json",
    )


def _read_decision(path: Path) -> tuple[dict[str, str] | None, str | None]:
    if not path.exists():
        return None, "reviewer did not write decision.json"
    try:
        value = read_json(path)
    except HarnessError as exc:
        return None, str(exc)
    decision = value.get("decision")
    next_task = value.get("next_task")
    why = value.get("why")
    if decision not in DECISIONS:
        return None, f"decision must be one of {', '.join(DECISIONS)}"
    if decision == "continue" and not (isinstance(next_task, str) and next_task.strip()):
        return None, "continue requires next_task"
    if not (isinstance(why, str) and why.strip()):
        return None, "why is required"
    findings, dropped, error = normalize_findings(value.get("findings", []))
    if error:
        return None, error
    review = value.get("review")
    if review is not None and not isinstance(review, str):
        return None, "review must be a string"
    return {
        "decision": decision,
        "next_task": next_task if isinstance(next_task, str) else None,
        "why": why.strip(),
        "findings": findings,
        "dropped": dropped,
        "review": review,
    }, None


def run_review(root: Path, *, objection: str | None = None) -> dict[str, Any]:
    root = root.resolve()
    with state_lock(root):
        config, state = load_runtime(root)
        reviewer = config.get("reviewer")
        if not reviewer:
            raise HarnessError(
                f"no reviewer configured; add {REVIEWER_FILE} before init"
            )
        if not state.get("active"):
            raise HarnessError("harness is disabled")
        if state.get("phase") != Phase.VERIFIED.value:
            raise HarnessError("review runs only after the task is verified")
        request = pause_request(root)
        if request:
            raise HarnessError(f"runner is paused: {request['reason']}")
        if state.get("review_running"):
            raise HarnessError(_review_in_progress(state))

        previous = state.get("review") or {}
        if previous.get("verify_run_id") == state.get("last_run_id"):
            if previous.get("decision") and not objection:
                raise HarnessError(
                    "task is already reviewed; pass --objection with a factual error"
                )
            if int(previous.get("attempts", 0)) >= MAX_REVIEWS:
                raise HarnessError("review attempts exhausted; ask the human")
        else:
            if objection:
                raise HarnessError("there is no review decision to object to")
            if state.get("verified_fingerprint") != workspace_fingerprint(root):
                raise HarnessError("verification is stale; rerun verify first")
            previous = {"verify_run_id": state["last_run_id"], "attempts": 0}

        review_dir = _review_dir(root)
        review_dir.mkdir(parents=True, exist_ok=True)
        decision_path = review_dir / "decision.json"
        decision_path.unlink(missing_ok=True)
        (review_dir / "prompt.md").write_text(
            _prompt(root, config, state, previous, objection), encoding="utf-8"
        )

        run_id = new_run_id()
        run_dir = harness_dir(root) / "artifacts" / run_id
        run_dir.mkdir(parents=True)
        state["review_running"] = {"run_id": run_id, "pid": os.getpid()}
        atomic_write_json(harness_dir(root) / STATE_FILE, state)

    argv = list(reviewer["argv"])
    execution = execute_process(
        root,
        argv,
        timeout_seconds=float(reviewer["timeout_seconds"]),
        run_dir=run_dir,
        max_output_bytes=int(config["limits"]["max_output_bytes"]),
        is_paused=lambda: pause_request(root) is not None,
    )
    result: dict[str, Any] = {
        "version": 1,
        "run_id": run_id,
        "task_id": state["task_id"],
        "kind": "review",
        "argv": argv,
        "cwd": str(root),
        **execution,
    }

    with state_lock(root):
        current_config, current = load_runtime(root)
        if (current.get("review_running") or {}).get("run_id") != run_id or (
            current["task_id"] != state["task_id"]
        ):
            atomic_write_json(run_dir / "result.json", result)
            append_journal(root, result, int(current_config["limits"]["max_journal_entries"]))
            raise HarnessError(
                f"state changed while task reviewer run {run_id} was running; result journaled, state kept"
            )
        config, state = current_config, current
        state.pop("review_running", None)
        if result["outcome"] == "pass":
            decision, error = _read_decision(decision_path)
        else:
            decision, error = None, f"reviewer {result['outcome']}"
        if decision and decision["next_task"]:
            next_task = str(decision["next_task"])
            status = active_task_status(root, next_task) or ""
            if not status or any(marker in status for marker in CLOSED_MARKERS):
                decision = None
                error = f"next task {next_task} must be an open task in the task list"
        if decision:
            close_task(
                root, config.get("plan_doc"), str(state["task_id"]), decision.pop("review")
            )

        review = {
            "verify_run_id": previous["verify_run_id"],
            "attempts": int(previous.get("attempts", 0)) + 1,
            "run_id": run_id,
            "decision": None,
            "next_task": None,
            "why": None,
            "error": error,
            "at": utc_now(),
        }
        if decision:
            review.update(decision)
            if decision["next_task"]:
                from harness.plan_review import record_task_review, task_record

                if not task_record(root, str(decision["next_task"]))["reviews"]:
                    record_task_review(
                        root,
                        str(decision["next_task"]),
                        findings=[],
                        dropped=0,
                        summary=decision["why"],
                        source="task_review",
                        run_id=run_id,
                    )
        elif previous.get("decision"):
            review.update(
                {key: previous[key] for key in ("decision", "next_task", "why")}
            )
        state["review"] = review
        state["updated_at"] = utc_now()
        atomic_write_json(run_dir / "result.json", result)
        atomic_write_json(harness_dir(root) / STATE_FILE, state)
        append_journal(root, result, int(config["limits"]["max_journal_entries"]))
        prune_artifacts(root, int(config["limits"]["max_artifacts"]))
        return {"result": result, "review": review}


def _review_in_progress(state: dict[str, Any]) -> str:
    running = state.get("review_running") or {}
    return (
        f"task reviewer run {running.get('run_id')} for {state['task_id']} is in progress "
        f"(pid {running.get('pid')}); wait for it to finish"
    )


def review_followup(
    root: Path,
    config: dict[str, Any],
    state: dict[str, Any],
    state_path: Path,
) -> str | None:
    runner = Path(__file__).with_name("run.py")
    command = f'python "{runner}" --root "{root.resolve()}" review'
    if state.get("review_running"):
        return _review_in_progress(state)
    review = state.get("review") or {}
    if review.get("verify_run_id") != state.get("last_run_id"):
        if not config.get("reviewer"):
            return None
        return (
            f"Task {state['task_id']} is verified. The next step belongs to the "
            f"reviewer, not to you. Run: {command}"
        )
    if review.get("decision") == "continue":
        objection = (
            f' If one exists, run once: {command} --objection "<the fact>".'
            if int(review.get("attempts", 0)) < MAX_REVIEWS
            else ""
        )
        findings = describe(review.get("findings") or [])
        return (
            f"Reviewer chose continue -> {review['next_task']}: {review['why']}. {findings} "
            "Read the updated task list and check the rewrite only for factual "
            "errors (wrong path or number, already done, cannot run here, over "
            f"budget).{objection} Otherwise initialize the Harness for "
            f"{review['next_task']} and execute it."
        )
    if review.get("decision"):
        return None
    if int(review.get("attempts", 0)) < MAX_REVIEWS:
        return (
            f"Reviewer run failed: {review.get('error')}. Repair the reviewer "
            f"command or environment, then run: {command}"
        )
    if review.get("report_requested"):
        return None
    review["report_requested"] = True
    state["updated_at"] = utc_now()
    atomic_write_json(state_path, state)
    return (
        f"Reviewer failed {MAX_REVIEWS} times ({review.get('error')}). Do not "
        "choose the next task yourself; report the reviewer error to the human "
        "and stop."
    )
