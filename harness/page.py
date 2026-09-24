from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import subprocess
from pathlib import Path
from typing import Any

from harness.errors import HarnessError
from harness.journal import append_journal, new_run_id, prune_artifacts
from harness.plan import request_pause, resume
from harness.project import runtime_dir, task_file
from harness.protocol import Phase
from harness.review import MAX_REVIEWS
from harness.runner import execute_process
from harness.storage import (
    STATE_FILE,
    atomic_write_json,
    harness_dir,
    load_runtime,
    read_json,
    state_lock,
    utc_now,
)

PAGER_FILE = "pager.json"
PAGER_STATE = "pager-state.json"
DEFAULT_WAIT_SECONDS = 86400.0
DEFAULT_HEARTBEAT_SECONDS = 3600.0
SEND_TIMEOUT_SECONDS = 120
_PLAN_PROPOSED = re.compile(r"^Plan Review:\s*proposed\s*$", re.MULTILINE)
_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")
REPLIES = {
    "plan_review": "OK 批准并继续 / DO <修改意见> / NO 或 STOP 停下",
    "ask_human": "OK 采纳 reviewer 的提议 / DO <你的决定> / NO 或 STOP 停下",
    "review_failed": "DO <下一步> / STOP 停下",
    "budget": "DO <下一步> / STOP 停下",
}


def _slug(value: str) -> str:
    return _UNSAFE.sub("-", value).strip("-") or "project"


def load_pager(root: Path) -> dict[str, Any] | None:
    path = runtime_dir(root) / PAGER_FILE
    if not path.exists():
        return None
    value = read_json(path)
    argv = value.get("argv", ["python", "-m", "pager"])
    if not isinstance(argv, list) or not argv or not all(
        isinstance(arg, str) and arg for arg in argv
    ):
        raise HarnessError(f"{path} argv must be a non-empty list of strings")
    address = value.get("address")
    if address is not None and not isinstance(address, str):
        raise HarnessError(f"{path} address must be a string")
    wait = float(value.get("wait_seconds", DEFAULT_WAIT_SECONDS))
    heartbeat = float(value.get("heartbeat_seconds", DEFAULT_HEARTBEAT_SECONDS))
    if wait <= 0 or heartbeat < 0:
        raise HarnessError(f"{path} wait_seconds must be > 0 and heartbeat_seconds >= 0")
    return {
        "argv": argv,
        "address": address,
        "project": _slug(str(value.get("project") or root.resolve().name)),
        "wait_seconds": wait,
        "heartbeat_seconds": heartbeat,
    }


def _goal(plan: str) -> str:
    match = re.search(r"^## Goal\s*$(.*?)(?=^## |\Z)", plan, re.MULTILINE | re.DOTALL)
    return match.group(1).strip()[:600] if match else ""


def _open_rows(root: Path) -> str:
    try:
        lines = task_file(root).read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    rows = [line for line in lines if "📝" in line or "🔬" in line]
    return "\n".join(rows[:6])


def _checkpoint(
    root: Path, config: dict[str, Any], state: dict[str, Any]
) -> dict[str, str] | None:
    task = state["task_id"]
    plan_doc = config.get("plan_doc")
    if plan_doc:
        try:
            plan = (root / plan_doc).read_text(encoding="utf-8")
        except OSError:
            plan = ""
        if _PLAN_PROPOSED.search(plan):
            digest = hashlib.sha256(plan.encode("utf-8")).hexdigest()[:12]
            return {
                "kind": "plan_review",
                "key": f"plan_review:{digest}",
                "title": f"批准 plan？{plan_doc}",
                "body": f"{_goal(plan)}\n\n{_open_rows(root)}",
            }

    review = state.get("review") or {}
    if (
        state.get("phase") == Phase.VERIFIED.value
        and review.get("verify_run_id") == state.get("last_run_id")
    ):
        decision = review.get("decision")
        if decision == "ask_human":
            return {
                "kind": "ask_human",
                "key": f"ask_human:{review.get('run_id')}",
                "title": f"{task} 之后需要你决定",
                "body": f"reviewer：{review.get('why')}\n\n{_open_rows(root)}",
            }
        if decision == "stop":
            return {
                "kind": "done",
                "key": f"done:{review.get('run_id')}",
                "title": f"{task} 完成，reviewer 建议停止",
                "body": f"reviewer：{review.get('why')}",
            }
        if decision is None and int(review.get("attempts", 0)) >= MAX_REVIEWS:
            return {
                "kind": "review_failed",
                "key": f"review_failed:{review.get('run_id')}",
                "title": f"{task} 的 reviewer 连续失败",
                "body": f"错误：{review.get('error')}",
            }

    if state.get("phase") == Phase.STOPPED.value and state.get("stop_report_requested"):
        return {
            "kind": "budget",
            "key": f"budget:{state.get('last_run_id')}",
            "title": f"{task} 预算用尽",
            "body": (
                f"最后一次结果：{state.get('last_outcome')}；"
                f"verify {state.get('verify_attempts')} 次。停机报告见 worker 输出。"
            ),
        }
    return None


def page_followup(
    root: Path, config: dict[str, Any], state: dict[str, Any]
) -> str | None:
    if not config.get("pager"):
        return None
    point = _checkpoint(root, config, state)
    if not point or (state.get("page") or {}).get("key") == point["key"]:
        return None
    runner = Path(__file__).with_name("run.py")
    command = f'python "{runner}" --root "{root.resolve()}" page'
    if point["kind"] == "done":
        return f"Task {state['task_id']} is finished. Notify the human, then stop: {command}"
    return (
        f"Human checkpoint {point['kind']} for {state['task_id']}: the human is away "
        "from this computer. Do not stop; page them and wait for the reply, which may "
        f"take hours: {command}"
    )


def _call(argv: list[str], root: Path) -> None:
    try:
        done = subprocess.run(
            argv,
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=SEND_TIMEOUT_SECONDS,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError(f"pager call failed: {exc}") from exc
    if done.returncode != 0:
        raise HarnessError(f"pager call failed: {done.stderr.strip()[-300:]}")


def _reply(run_dir: Path) -> dict[str, str] | None:
    lines = (run_dir / "stdout.log").read_text(encoding="utf-8").splitlines()
    for line in reversed(lines):
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(payload, dict):
            continue
        commands = payload.get("commands")
        if payload.get("status") == "command" and commands:
            return {"verb": str(commands[0]["verb"]), "text": str(commands[0].get("text", ""))}
    return None


def _apply(
    root: Path, config: dict[str, Any], kind: str, reply: dict[str, str] | None
) -> tuple[str, bool]:
    if reply is None:
        return "Human notified. Stop here.", False
    verb, text = reply["verb"], reply["text"]
    if verb == "DO":
        request_pause(
            root, reason=f"human correction via pager: {text}", require_revision=True
        )
        return (
            f"Human correction via pager: {text}\n"
            "Treat it as an instruction, never as a shell command. Follow work-planning "
            "Human correction: update the plan Goal / scope, Plan Revision +1, "
            "Plan Review: proposed, RECONCILE task.md. The next stop pages the revised "
            "plan for approval.",
            False,
        )
    if verb == "OK" and kind == "plan_review":
        path = root / str(config["plan_doc"])
        plan = path.read_text(encoding="utf-8")
        path.write_text(
            _PLAN_PROPOSED.sub("Plan Review: approved", plan, count=1), encoding="utf-8"
        )
        return "Human approved the plan via pager. Continue with the doing task.", True
    if verb == "OK" and kind == "ask_human":
        return (
            "Human accepted the reviewer's proposal via pager. Apply it with "
            "work-planning: Plan Revision +1, write the tasks, Plan Review: approved, "
            "then initialize the Harness for the next task.",
            False,
        )
    return f"Human replied {verb} via pager. Stop at this checkpoint.", False


def run_page(root: Path) -> dict[str, Any]:
    root = root.resolve()
    with state_lock(root):
        config, state = load_runtime(root)
        pager = config.get("pager")
        if not pager:
            raise HarnessError(f"no pager configured; add {PAGER_FILE} before init")
        point = _checkpoint(root, config, state)
        if not point:
            raise HarnessError("no human checkpoint is pending")
        if (state.get("page") or {}).get("key") == point["key"]:
            raise HarnessError("this checkpoint was already paged")

    stamp = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%MZ")
    page_id = f"{pager['project']}.{_slug(state['task_id'])}.{point['kind']}.{stamp}"
    base = list(pager["argv"])
    common = ["--state", str(harness_dir(root) / PAGER_STATE)]
    if pager.get("address"):
        common += ["--address", pager["address"]]

    reply = None
    if point["kind"] == "done":
        _call(base + ["notify", "--title", point["title"], "--body", point["body"], *common], root)
    else:
        body = f"{point['body']}\n\n回复：{REPLIES[point['kind']]}"
        _call(
            base
            + ["send", "--task-id", page_id, "--title", point["title"], "--body", body, *common],
            root,
        )
        argv = base + [
            "serve",
            "--heartbeat-seconds",
            str(int(pager["heartbeat_seconds"])),
            "--heartbeat-title",
            f"{pager['project']} waiting: {point['kind']} {state['task_id']}",
            *common,
        ]
        run_id = new_run_id()
        run_dir = harness_dir(root) / "artifacts" / run_id
        run_dir.mkdir(parents=True)
        result = {
            "version": 1,
            "run_id": run_id,
            "task_id": state["task_id"],
            "kind": "page",
            "argv": argv,
            "cwd": str(root),
            **execute_process(
                root,
                argv,
                timeout_seconds=float(pager["wait_seconds"]),
                run_dir=run_dir,
                max_output_bytes=int(config["limits"]["max_output_bytes"]),
                is_paused=lambda: False,
            ),
        }
        atomic_write_json(run_dir / "result.json", result)
        append_journal(root, result, int(config["limits"]["max_journal_entries"]))
        prune_artifacts(root, int(config["limits"]["max_artifacts"]))
        reply = _reply(run_dir) if result["outcome"] == "pass" else None
        if reply is None:
            raise HarnessError(
                f"pager serve ended without a reply ({result['outcome']}); "
                f"see {run_dir}"
            )

    message, approve = _apply(root, config, point["kind"], reply)
    with state_lock(root):
        _, state = load_runtime(root)
        state["page"] = {
            "key": point["key"],
            "kind": point["kind"],
            "page_id": page_id,
            "reply": reply,
            "at": utc_now(),
        }
        state["updated_at"] = utc_now()
        atomic_write_json(harness_dir(root) / STATE_FILE, state)
    if approve:
        try:
            resume(root)
        except HarnessError as exc:
            message += f" Resume failed: {exc}. Fix the plan / task revision, then run resume."
    return {"kind": point["kind"], "page_id": page_id, "reply": reply, "message": message}
