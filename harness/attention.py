from __future__ import annotations

import contextlib
import datetime as dt
from pathlib import Path
from typing import Any

from harness.errors import HarnessError
from harness.plan import PAUSE_FILE, pause_request, plan_can_run, request_pause
from harness.protocol import Event, Phase, TransitionError, apply_event
from harness.storage import (
    STATE_FILE,
    atomic_write_json,
    harness_dir,
    load_runtime,
    state_lock,
    utc_now,
)

DEFAULT_AFTER_ACTIONS = 3
DEFAULT_AFTER_SECONDS = 3600.0


def settings(config: dict[str, Any]) -> dict[str, Any]:
    value = config.get("goal_review", {})
    return {
        "after_actions": int(value.get("after_actions", DEFAULT_AFTER_ACTIONS)),
        "after_seconds": float(value.get("after_seconds", DEFAULT_AFTER_SECONDS)),
        "on_failure": bool(value.get("on_failure", True)),
    }


def goal_review_reason(
    config: dict[str, Any],
    state: dict[str, Any],
    result: dict[str, Any],
) -> str | None:
    policy = settings(config)
    if policy["on_failure"] and result["outcome"] in {
        "fail",
        "timeout",
        "error",
        "reject",
    }:
        return f"goal_review_due: {result['outcome']}"
    if int(state.get("actions_since_goal_review", 0)) >= policy["after_actions"]:
        return (
            "goal_review_due: "
            f"{state['actions_since_goal_review']} actions since review"
        )
    last = state.get("last_goal_review_at") or state.get("created_at")
    try:
        elapsed = (
            dt.datetime.now(dt.UTC) - dt.datetime.fromisoformat(str(last))
        ).total_seconds()
    except ValueError:
        elapsed = policy["after_seconds"]
    if elapsed >= policy["after_seconds"]:
        return f"goal_review_due: {elapsed:.0f}s since review"
    return None


def schedule_goal_review(root: Path, reason: str) -> None:
    request_pause(root, reason=reason, kind="goal_review")


def record_goal_review(
    root: Path,
    *,
    decision: str,
    evidence: str,
) -> dict[str, Any]:
    if decision not in {"continue", "replan", "stop"}:
        raise HarnessError("goal review decision must be continue, replan, or stop")
    if not evidence.strip():
        raise HarnessError("goal review evidence is required")

    with state_lock(root):
        config, state = load_runtime(root)
        request = pause_request(root)
        if not request or request.get("kind") != "goal_review":
            raise HarnessError("no Goal Review is pending")
        state["last_goal_review"] = {
            "at": utc_now(),
            "decision": decision,
            "evidence": evidence,
        }

        if decision == "continue":
            if request.get("require_revision"):
                raise HarnessError("this pause requires Plan Revision to increase")
            plan_ready, reason = plan_can_run(root, config, state)
            if not plan_ready:
                raise HarnessError(reason or "plan is not ready")
            try:
                if state.get("phase") != Phase.PAUSED.value:
                    apply_event(state, Event.PAUSE_REQUESTED)
                apply_event(state, Event.PLAN_RESUMED)
            except TransitionError as exc:
                raise HarnessError(str(exc)) from exc
            state["actions_since_goal_review"] = 0
            state["last_goal_review_at"] = utc_now()
            state["verified_fingerprint"] = None
            with contextlib.suppress(OSError):
                (harness_dir(root) / PAUSE_FILE).unlink()
        elif decision == "replan":
            request["kind"] = "human"
            request["require_revision"] = True
            request["reason"] = "Goal Review chose replan"
            request["updated_at"] = utc_now()
            atomic_write_json(harness_dir(root) / PAUSE_FILE, request)
        else:
            try:
                apply_event(state, Event.DISABLED)
            except TransitionError as exc:
                raise HarnessError(str(exc)) from exc
            state["active"] = False
            with contextlib.suppress(OSError):
                (harness_dir(root) / PAUSE_FILE).unlink()

        state["updated_at"] = utc_now()
        atomic_write_json(harness_dir(root) / STATE_FILE, state)
        return state

