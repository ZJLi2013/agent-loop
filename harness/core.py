from __future__ import annotations

import contextlib
import hashlib
import os
import re
import subprocess
from pathlib import Path
from typing import Any

from harness.attention import (
    DEFAULT_AFTER_ACTIONS,
    DEFAULT_AFTER_SECONDS,
    goal_review_reason,
    schedule_goal_review,
)
from harness.errors import HarnessError
from harness.journal import (
    append_journal,
    new_run_id,
    prune_artifacts,
)
from harness.plan import (
    PAUSE_FILE,
    current_plan,
    pause_request,
    plan_can_run,
    plan_metadata,
    request_pause,
    resume,
    task_plan_revision,
)
from harness.protocol import Event, Phase, TransitionError, apply_event
from harness.runner import execute_process
from harness.storage import (
    CONFIG_FILE,
    HARNESS_DIR,
    STATE_FILE,
    atomic_write_json,
    config_digest,
    harness_dir,
    load_runtime,
    read_json,
    state_lock,
    utc_now,
)

DEFAULT_TIMEOUT_SECONDS = 300.0
DEFAULT_MAX_ATTEMPTS = 3
DEFAULT_MAX_WALL_SECONDS = 1800.0
DEFAULT_MAX_OUTPUT_BYTES = 1_048_576
DEFAULT_MAX_ARTIFACTS = 20
DEFAULT_MAX_JOURNAL_ENTRIES = 1000


def _transition(state: dict[str, Any], event: Event) -> None:
    try:
        apply_event(state, event)
    except TransitionError as exc:
        raise HarnessError(str(exc)) from exc


def initialize(
    root: Path,
    *,
    task_id: str,
    verifier_argv: list[str],
    plan_doc: str | None = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    max_attempts: int = DEFAULT_MAX_ATTEMPTS,
    max_wall_seconds: float = DEFAULT_MAX_WALL_SECONDS,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_artifacts: int = DEFAULT_MAX_ARTIFACTS,
    max_journal_entries: int = DEFAULT_MAX_JOURNAL_ENTRIES,
    goal_review_after_actions: int = DEFAULT_AFTER_ACTIONS,
    goal_review_after_seconds: float = DEFAULT_AFTER_SECONDS,
    goal_review_on_failure: bool = True,
    expect_regex: str | None = None,
    forbid_regex: str | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    if not task_id.strip():
        raise HarnessError("task_id is required")
    if not verifier_argv:
        raise HarnessError("verifier command is required")
    for label, pattern in (
        ("expect_regex", expect_regex),
        ("forbid_regex", forbid_regex),
    ):
        if pattern:
            try:
                re.compile(pattern)
            except re.error as exc:
                raise HarnessError(f"invalid {label}: {exc}") from exc
    if min(
        timeout_seconds,
        max_attempts,
        max_wall_seconds,
        max_output_bytes,
        max_artifacts,
        max_journal_entries,
        goal_review_after_actions,
        goal_review_after_seconds,
    ) <= 0:
        raise HarnessError("timeouts, budgets, and limits must be positive")

    root = root.resolve()
    base = harness_dir(root)
    state_path = base / STATE_FILE
    if state_path.exists():
        old = read_json(state_path)
        if old.get("active") and old.get("phase") not in {
            Phase.VERIFIED.value,
            Phase.STOPPED.value,
            Phase.PAUSED.value,
        }:
            raise HarnessError(
                f"task {old.get('task_id')} is still active; finish or disable it first"
            )

    revision: int | None = None
    review: str | None = None
    if plan_doc:
        revision, review = plan_metadata(root, plan_doc)
        task_revision = task_plan_revision(root, task_id)
        if task_revision != revision:
            raise HarnessError(
                f"task {task_id} binds r{task_revision}, plan is r{revision}"
            )

    created_at = utc_now()
    config: dict[str, Any] = {
        "version": 1,
        "task_id": task_id,
        "plan_doc": plan_doc,
        "verifier": {
            "argv": verifier_argv,
            "timeout_seconds": float(timeout_seconds),
            "expect_regex": expect_regex,
            "forbid_regex": forbid_regex,
        },
        "budget": {
            "max_attempts": int(max_attempts),
            "max_wall_seconds": float(max_wall_seconds),
        },
        "limits": {
            "max_output_bytes": int(max_output_bytes),
            "max_artifacts": int(max_artifacts),
            "max_journal_entries": int(max_journal_entries),
        },
        "goal_review": {
            "after_actions": int(goal_review_after_actions),
            "after_seconds": float(goal_review_after_seconds),
            "on_failure": bool(goal_review_on_failure),
        },
        "created_at": created_at,
    }
    phase = Phase.PROPOSED if review == "proposed" else Phase.READY
    state: dict[str, Any] = {
        "version": 1,
        "task_id": task_id,
        "active": True,
        "phase": phase.value,
        "plan_revision": revision,
        "plan_review": review,
        "verify_attempts": 0,
        "wall_seconds_used": 0.0,
        "current_run_id": None,
        "last_run_id": None,
        "last_outcome": None,
        "actions_since_goal_review": 0,
        "last_goal_review_at": created_at,
        "last_goal_review": None,
        "verified_fingerprint": None,
        "stop_report_requested": False,
        "config_sha256": config_digest(config),
        "created_at": created_at,
        "updated_at": created_at,
    }
    base.mkdir(parents=True, exist_ok=True)
    atomic_write_json(base / CONFIG_FILE, config)
    atomic_write_json(state_path, state)
    (base / "artifacts").mkdir(exist_ok=True)
    with contextlib.suppress(OSError):
        (base / PAUSE_FILE).unlink()
    if review == "proposed":
        request_pause(
            root,
            reason=f"{plan_doc} is awaiting Human Review",
        )
        _transition(state, Event.PAUSE_REQUESTED)
        state["updated_at"] = utc_now()
        atomic_write_json(state_path, state)
    _exclude_runtime_from_git(root)
    return config, state


def _exclude_runtime_from_git(root: Path) -> None:
    git_dir = root.resolve() / ".git"
    if not git_dir.is_dir():
        return
    exclude = git_dir / "info" / "exclude"
    exclude.parent.mkdir(parents=True, exist_ok=True)
    current = exclude.read_text(encoding="utf-8") if exclude.exists() else ""
    entry = f"/{HARNESS_DIR}/"
    if entry not in current.splitlines():
        separator = "" if not current or current.endswith("\n") else "\n"
        with exclude.open("a", encoding="utf-8") as fh:
            fh.write(f"{separator}{entry}\n")


def _remaining_wall(config: dict[str, Any], state: dict[str, Any]) -> float:
    maximum = float(config["budget"]["max_wall_seconds"])
    return maximum - float(state["wall_seconds_used"])


def _budget_exhausted(
    config: dict[str, Any],
    state: dict[str, Any],
) -> bool:
    return (
        int(state["verify_attempts"]) >= int(config["budget"]["max_attempts"])
        or _remaining_wall(config, state) <= 0
    )


def run_command(
    root: Path,
    argv: list[str],
    *,
    kind: str,
    timeout_seconds: float | None = None,
) -> dict[str, Any]:
    if not argv:
        raise HarnessError("command is required")
    if kind not in {"exec", "verify"}:
        raise HarnessError(f"unsupported run kind: {kind}")

    root = root.resolve()
    with state_lock(root):
        config, state = load_runtime(root)
        if not state.get("active"):
            raise HarnessError("harness is disabled")
        request = pause_request(root)
        if request:
            if state.get("phase") != Phase.PAUSED.value:
                _transition(state, Event.PAUSE_REQUESTED)
            state["updated_at"] = utc_now()
            atomic_write_json(harness_dir(root) / STATE_FILE, state)
            raise HarnessError(f"runner is paused: {request['reason']}")
        plan_ready, plan_reason = plan_can_run(root, config, state)
        if not plan_ready:
            request_pause(
                root,
                reason=plan_reason or "plan is not approved",
                require_revision="revision changed" in (plan_reason or ""),
            )
            _transition(state, Event.PAUSE_REQUESTED)
            state["updated_at"] = utc_now()
            atomic_write_json(harness_dir(root) / STATE_FILE, state)
            raise HarnessError(f"runner is paused: {plan_reason}")
        attention_reason = goal_review_reason(
            config, state, {"outcome": "pass"}
        )
        if attention_reason:
            schedule_goal_review(root, attention_reason)
            _transition(state, Event.PAUSE_REQUESTED)
            state["updated_at"] = utc_now()
            atomic_write_json(harness_dir(root) / STATE_FILE, state)
            raise HarnessError(f"runner is paused: {attention_reason}")
        if _budget_exhausted(config, state):
            if state.get("phase") != Phase.STOPPED.value:
                _transition(state, Event.BUDGET_EXHAUSTED)
                state["updated_at"] = utc_now()
                atomic_write_json(harness_dir(root) / STATE_FILE, state)
            raise HarnessError("execution budget exhausted")

        requested = (
            float(timeout_seconds)
            if timeout_seconds is not None
            else float(config["verifier"]["timeout_seconds"])
        )
        if requested <= 0:
            raise HarnessError("timeout must be positive")
        timeout = min(requested, _remaining_wall(config, state))
        run_id = new_run_id()
        run_dir = harness_dir(root) / "artifacts" / run_id
        run_dir.mkdir(parents=True)
        _transition(
            state,
            Event.VERIFY_STARTED if kind == "verify" else Event.RUN_STARTED,
        )
        state["current_run_id"] = run_id
        state["updated_at"] = utc_now()
        atomic_write_json(harness_dir(root) / STATE_FILE, state)

        execution = execute_process(
            root,
            argv,
            timeout_seconds=timeout,
            run_dir=run_dir,
            max_output_bytes=int(config["limits"]["max_output_bytes"]),
            is_paused=lambda: pause_request(root) is not None,
        )
        result: dict[str, Any] = {
            "version": 1,
            "run_id": run_id,
            "task_id": state["task_id"],
            "kind": kind,
            "argv": argv,
            "cwd": str(root),
            **execution,
        }

        state["wall_seconds_used"] = round(
            float(state["wall_seconds_used"])
            + float(result["duration_seconds"]),
            6,
        )
        state["current_run_id"] = None
        state["last_run_id"] = run_id

        if result["paused"]:
            _transition(state, Event.PAUSE_REQUESTED)
            state["verified_fingerprint"] = None
        elif kind == "verify":
            state["verify_attempts"] = int(state["verify_attempts"]) + 1
            contract_passed = (
                result["outcome"] == "pass"
                and _matches_contract(config, run_dir)
            )
            result["verification_passed"] = contract_passed
            if contract_passed:
                _transition(state, Event.VERIFY_PASSED)
                state["verified_fingerprint"] = workspace_fingerprint(root)
            else:
                if result["outcome"] == "pass":
                    result["outcome"] = "reject"
                _transition(state, Event.VERIFY_FAILED)
                state["verified_fingerprint"] = None
                if _budget_exhausted(config, state):
                    _transition(state, Event.BUDGET_EXHAUSTED)
        else:
            event = (
                Event.RUN_FINISHED
                if result["outcome"] == "pass"
                else Event.RUN_FAILED
            )
            _transition(state, event)
            if _budget_exhausted(config, state):
                _transition(state, Event.BUDGET_EXHAUSTED)

        if not result["paused"]:
            state["actions_since_goal_review"] = int(
                state.get("actions_since_goal_review", 0)
            ) + 1
            if state.get("phase") != Phase.STOPPED.value:
                attention_reason = goal_review_reason(config, state, result)
                if attention_reason:
                    schedule_goal_review(root, attention_reason)
                    _transition(state, Event.PAUSE_REQUESTED)

        state["last_outcome"] = result["outcome"]
        state["updated_at"] = utc_now()
        atomic_write_json(run_dir / "result.json", result)
        atomic_write_json(harness_dir(root) / STATE_FILE, state)
        append_journal(
            root, result, int(config["limits"]["max_journal_entries"])
        )
        prune_artifacts(root, int(config["limits"]["max_artifacts"]))
        return result


def _matches_contract(
    config: dict[str, Any],
    run_dir: Path,
) -> bool:
    verifier = config["verifier"]
    expect = verifier.get("expect_regex")
    forbid = verifier.get("forbid_regex")
    if not expect and not forbid:
        return True
    output = (
        (run_dir / "stdout.log").read_text(encoding="utf-8")
        + "\n"
        + (run_dir / "stderr.log").read_text(encoding="utf-8")
    )
    if expect and not re.search(str(expect), output, flags=re.MULTILINE):
        return False
    if forbid and re.search(str(forbid), output, flags=re.MULTILINE):
        return False
    return True


def verify(root: Path) -> dict[str, Any]:
    config, _ = load_runtime(root)
    verifier = config["verifier"]
    return run_command(
        root,
        list(verifier["argv"]),
        kind="verify",
        timeout_seconds=float(verifier["timeout_seconds"]),
    )


def workspace_fingerprint(root: Path) -> str:
    root = root.resolve()
    digest = hashlib.sha256()
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        diff = subprocess.run(
            ["git", "diff", "--binary", "HEAD", "--", ".", f":(exclude){HARNESS_DIR}"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout
        untracked = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard", "-z"],
            cwd=root,
            check=True,
            capture_output=True,
        ).stdout.split(b"\0")
        digest.update(head)
        digest.update(diff)
        for raw_path in sorted(path for path in untracked if path):
            relative = raw_path.decode("utf-8", errors="surrogateescape")
            if relative == HARNESS_DIR or relative.startswith(f"{HARNESS_DIR}/"):
                continue
            digest.update(raw_path)
            path = root / relative
            if path.is_file():
                with path.open("rb") as fh:
                    for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                        digest.update(chunk)
        return digest.hexdigest()
    except (OSError, subprocess.CalledProcessError):
        return _fallback_fingerprint(root)


def _fallback_fingerprint(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if not path.is_file() or relative.parts[0] in {HARNESS_DIR, ".git"}:
            continue
        digest.update(str(relative).encode("utf-8", errors="surrogateescape"))
        with path.open("rb") as fh:
            for chunk in iter(lambda: fh.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def disable(root: Path) -> dict[str, Any]:
    with state_lock(root):
        state = read_json(harness_dir(root) / STATE_FILE)
        state["active"] = False
        _transition(state, Event.DISABLED)
        state["updated_at"] = utc_now()
        atomic_write_json(harness_dir(root) / STATE_FILE, state)
        with contextlib.suppress(OSError):
            (harness_dir(root) / PAUSE_FILE).unlink()
        return state


def completion_gate(root: Path) -> str | None:
    state_path = harness_dir(root) / STATE_FILE
    if not state_path.exists():
        return None
    with state_lock(root):
        try:
            config, state = load_runtime(root)
        except HarnessError as exc:
            return f"Harness state is invalid: {exc}. Repair it before completing."
        if not state.get("active"):
            return None

        request = pause_request(root)
        if request:
            if request.get("kind") == "goal_review":
                return (
                    f"Harness paused {state['task_id']} for Goal Review: "
                    f"{request['reason']}. Use work-planning and record "
                    "continue / replan / stop."
                )
            return None
        if state.get("phase") in {
            Phase.PAUSED.value,
            Phase.PROPOSED.value,
        }:
            return None

        plan_ready, plan_reason = plan_can_run(root, config, state)
        if not plan_ready:
            request_pause(
                root,
                reason=plan_reason or "plan is not approved",
                require_revision="revision changed" in (plan_reason or ""),
            )
            _transition(state, Event.PAUSE_REQUESTED)
            state["verified_fingerprint"] = None
            state["updated_at"] = utc_now()
            atomic_write_json(state_path, state)
            return (
                f"Harness paused {state['task_id']}: {plan_reason}. Reconcile the "
                "plan document and task.md, obtain review, then run resume."
            )

        attention_reason = goal_review_reason(
            config, state, {"outcome": "pass"}
        )
        if attention_reason:
            schedule_goal_review(root, attention_reason)
            _transition(state, Event.PAUSE_REQUESTED)
            state["updated_at"] = utc_now()
            atomic_write_json(state_path, state)
            return (
                f"Harness paused {state['task_id']} for Goal Review: "
                f"{attention_reason}. Use work-planning before continuing."
            )

        phase = Phase(str(state["phase"]))
        if phase == Phase.VERIFIED:
            if state.get("verified_fingerprint") == workspace_fingerprint(root):
                return None
            _transition(state, Event.EVIDENCE_STALE)
            schedule_goal_review(root, "goal_review_due: evidence stale")
            _transition(state, Event.PAUSE_REQUESTED)
            state["verified_fingerprint"] = None
            state["last_outcome"] = "stale"
            state["updated_at"] = utc_now()
            atomic_write_json(state_path, state)
            return (
                f"Harness verification for {state['task_id']} is stale because the "
                "workspace changed. Complete Goal Review before rerunning verifier."
            )

        if phase == Phase.STOPPED:
            if state.get("stop_report_requested"):
                return None
            state["stop_report_requested"] = True
            state["updated_at"] = utc_now()
            atomic_write_json(state_path, state)
            return (
                f"Harness budget for {state['task_id']} is exhausted. Do not retry. "
                "Write an Auto-Stop Report with the current position, attempts, "
                "and the first command for returning to the main path, then stop."
            )

        remaining_attempts = int(config["budget"]["max_attempts"]) - int(
            state["verify_attempts"]
        )
        remaining_wall = max(0.0, _remaining_wall(config, state))
        runner = Path(__file__).with_name("run.py")
        verify_command = f'python "{runner}" --root "{root.resolve()}" verify'
        if phase in {Phase.RUNNING, Phase.VERIFYING}:
            _transition(state, Event.INTERRUPTED)
            state["current_run_id"] = None
            state["last_outcome"] = "interrupted"
            state["updated_at"] = utc_now()
            atomic_write_json(state_path, state)
        return (
            f"Task {state['task_id']} is not independently verified "
            f"({remaining_attempts} attempts, {remaining_wall:.1f}s remain). "
            f"Diagnose or repair if needed, then run: {verify_command}"
        )

