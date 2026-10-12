from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from harness.errors import HarnessError
from harness.fingerprint import workspace_fingerprint
from harness.journal import append_journal, new_run_id, prune_artifacts
from harness.plan import pause_request
from harness.project import memory_dir, review_checklist, runtime_dir, task_file
from harness.protocol import Phase
from harness.records import active_task_status, archive_closed_tasks, archived_task_ids
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
HEADING = re.compile(r"^#{1,6}\s+(.*)$")

PROMPT = """# Task boundary review

你是 reviewer。task {task_id} 已通过独立验证。worker 在另一个上下文里执行；你只读落盘文件。

## 输入

{inputs}

只打开上面的输入、plan / task / 设计文档直接链接的文件，以及设计文档列出的被测代码；其余文件不作证据，
缺了就报证据缺失，不自行搜索；够下结论就停止阅读。结论以原始证据为准，不以 worker 的摘要为准。
判据只来自 Goal、输入里列出的 repo 检查表和设计文档显式链接的检查表；`archive/` 目录与
`*-archive.md` 里的内容只是历史，可作事实引用，不作判据。
{extra}
## Review contract

review 的单位是这个 verified task，不是实验记录的一次修改、判据的一个版本或一轮讨论。
只指出会改变 `continue / ask_human / stop` 或下一条命令的问题；没有新 evidence 时不重新审查
已接受的判据。没有这类问题就直接完成交接，不扩写一般性建议。

## 要做的事

1. 核对 plan document 与 task 列表里关于 {task_id} 的结论是否与原始证据一致，不一致就改正。
   同时核对实际交给被测方的题目、数据、样本或请求（落盘的产物，不是摘要）与设计一致，且仍在测
   Goal 要测的东西；有上述检查表时逐条对照。
2. 在 task 列表里把 {task_id} 标为 `✅ done`；Harness 会把 closed 行移到
   `.agent-loop/archive/tasks.md`。把 plan document 中以 {task_id} 开头的标题段（设计、结果、
   review 依据），连同紧贴标题前的 `<a id>` 行，追加到同目录的 `{plan_archive}`。锚点链接按
   锚点所在文件改写：留下的段落指向被移走锚点用 `{plan_archive_name}#…`，被移走的段落指向留下的
   锚点用 `{plan_name}#…`，其他文档的 `{plan_name}#…` 改为 `{plan_archive_name}#…`；文件相对链接不改。
   活跃 plan 只更新当前结论与下一步决策，并留一行指向 archive 的指针。
   plan 仍有这类标题时 Harness 判本次决策无效。
   写好下一个 `📝 proposed` task：最多一个未验证假设、验收检查点、
   失败去向、预算，并链接本地设计文档；plan 表格里的一行不算设计。只展开最近 1–2 项，新 task
   的 `rev` 沿用当前 plan revision。
   结果为否定或意外、或下一个 task 要换方向时，先核对 plan 是否已对照领域结论与业界已有解法；
   没有就让下一个 task 先补这次调研，而不是直接再跑一轮实验。
3. 选择 decision：
   - `continue`：Goal 与 scope 不变，下一个 task 已写好；
   - `ask_human`：需要改 Goal / scope，要在有显著权衡的方案间选型，或实际产物与设计不一致、
     不在测 Goal 要测的东西（要改设计，由 human 决定修正还是换方向）；
   - `stop`：Goal 已达成，或继续不再改变主线。
4. 只改 plan document、task 列表、`{plan_archive}`，以及其他文档里指向被移走锚点的链接；
   不改代码，不跑实验。task 列表保持原有表格、一行一个 task、原有状态词；本次 review 的推理与
   依据写进 {task_id} 的归档段，不写进活跃 plan 或 task 列表。

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


def _plan_archive(plan_doc: str) -> str:
    path = Path(plan_doc)
    return path.with_name(f"{path.stem}-archive{path.suffix}").as_posix()


def _closed_task_headings(text: str, task_id: str) -> list[str]:
    return [
        line.strip()
        for line in text.splitlines()
        if (match := HEADING.match(line))
        and re.split(r"[\s:：]", match.group(1).strip(), maxsplit=1)[0] == task_id
    ]


def _closed_plan_sections(
    root: Path, config: dict[str, Any], task_id: str
) -> str | None:
    plan_doc = config.get("plan_doc")
    if not plan_doc or not (root / plan_doc).is_file():
        return None
    text = (root / plan_doc).read_text(encoding="utf-8")
    headings = _closed_task_headings(text, task_id)
    if not headings:
        return None
    listed = ", ".join(f'"{heading}"' for heading in headings)
    return (
        f"plan document {plan_doc} still has sections of closed task {task_id}: "
        f"{listed}; move them to {_plan_archive(plan_doc)}"
    )


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
    plan_doc = config.get("plan_doc")
    archive = _plan_archive(plan_doc) if plan_doc else "<plan>-archive.md"
    return PROMPT.format(
        task_id=state["task_id"],
        inputs="\n".join(inputs),
        extra=extra,
        decision_file=f"{HARNESS_DIR}/{REVIEW_DIR}/decision.json",
        plan_name=Path(plan_doc).name if plan_doc else "<plan>.md",
        plan_archive=archive,
        plan_archive_name=Path(archive).name,
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
        archived = []
        if decision and decision["decision"] == "continue":
            next_task = str(decision["next_task"])
            if "📝 proposed" not in (active_task_status(root, next_task) or ""):
                decision = None
                error = f"next task {next_task} must be 📝 proposed"
        if decision:
            archived = archive_closed_tasks(root)
            if str(state["task_id"]) not in archived_task_ids(root):
                decision = None
                error = (
                    f"reviewer must mark task {state['task_id']} as "
                    "✅ done or ❌ dropped"
                )
        result["archived_tasks"] = archived
        leftover = _closed_plan_sections(root, config, str(state["task_id"]))
        if leftover:
            decision = None
            error = f"{error}; {leftover}" if error else leftover

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
        elif previous.get("decision") and not leftover:
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
