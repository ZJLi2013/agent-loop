from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from harness.errors import HarnessError
from harness.fingerprint import workspace_fingerprint
from harness.journal import append_journal, new_run_id, prune_artifacts
from harness.plan import pause_request
from harness.project import memory_dir, runtime_dir, task_file
from harness.protocol import Phase
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

PROMPT = """# Task boundary review

你是 reviewer。task {task_id} 已通过独立验证。worker 在另一个上下文里执行；你只读落盘文件。

## 输入

{inputs}

按需打开 plan / task 引用的原始证据。结论以原始证据为准，不以 worker 的摘要为准。
{extra}
## 要做的事

1. 核对 plan document 与 task 列表里关于 {task_id} 的结论是否与原始证据一致，不一致就改正。
2. 在 task 列表里把 {task_id} 标为完成；写好下一个 task：最多一个未验证假设、验收检查点、
   失败去向、预算。只展开最近 1–2 项，新 task 的 `rev` 沿用当前 plan revision。
3. 选择 decision：
   - `continue`：Goal 与 scope 不变，下一个 task 已写好；
   - `ask_human`：需要改 Goal / scope，或要在有显著权衡的方案间选型；
   - `stop`：Goal 已达成，或继续不再改变主线。
4. 只改 plan document 与 task 列表；不改代码，不跑实验。task 列表保持原有表格、一行一个 task、
   原有状态词；推理与依据写进 plan document，不写进 task 列表。

## 输出

把下面的 JSON 写到 `{decision_file}`：

```json
{{"decision": "continue | ask_human | stop", "next_task": "<task id，continue 时必填>", "why": "<一句话：为什么这一步推进 Goal>"}}
```
"""


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
    extra = ""
    if objection:
        decision = {key: previous.get(key) for key in ("decision", "next_task", "why")}
        extra = (
            "\n## worker 的事实异议\n\n"
            f"上一次决策：`{json.dumps(decision, ensure_ascii=False)}`\n\n"
            f"{objection}\n\n核实后改正或维持；仍有分歧就选 `ask_human`。\n"
        )
    return PROMPT.format(
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
    return {
        "decision": decision,
        "next_task": next_task if isinstance(next_task, str) else None,
        "why": why.strip(),
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
        if result["outcome"] == "pass":
            decision, error = _read_decision(decision_path)
        else:
            decision, error = None, f"reviewer {result['outcome']}"

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


def review_followup(
    root: Path,
    config: dict[str, Any],
    state: dict[str, Any],
    state_path: Path,
) -> str | None:
    runner = Path(__file__).with_name("run.py")
    command = f'python "{runner}" --root "{root.resolve()}" review'
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
        return (
            f"Reviewer chose continue -> {review['next_task']}: {review['why']}. "
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
