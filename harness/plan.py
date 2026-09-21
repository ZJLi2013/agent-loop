from __future__ import annotations

import contextlib
import re
from pathlib import Path
from typing import Any

from harness.errors import HarnessError
from harness.protocol import Event, TransitionError, apply_event
from harness.storage import (
    STATE_FILE,
    atomic_write_json,
    harness_dir,
    load_runtime,
    read_json,
    state_lock,
    utc_now,
)

PAUSE_FILE = "pause.json"
_PLAN_REVISION_RE = re.compile(r"^Plan Revision:\s*(\d+)\s*$", re.MULTILINE)
_PLAN_REVIEW_RE = re.compile(
    r"^Plan Review:\s*(proposed|approved|unreviewed)\s*$",
    re.MULTILINE,
)


def plan_metadata(root: Path, plan_path: str) -> tuple[int, str]:
    root = root.resolve()
    plan = (root / plan_path).resolve()
    try:
        plan.relative_to(root)
    except ValueError as exc:
        raise HarnessError("plan path must stay inside the project root") from exc
    try:
        content = plan.read_text(encoding="utf-8")
    except OSError as exc:
        raise HarnessError(f"cannot read plan document {plan_path}: {exc}") from exc
    revision = _PLAN_REVISION_RE.search(content)
    review = _PLAN_REVIEW_RE.search(content)
    if not revision or not review:
        raise HarnessError(
            f"{plan_path} must contain 'Plan Revision: N' and "
            "'Plan Review: proposed|approved|unreviewed'"
        )
    return int(revision.group(1)), review.group(1)


def task_plan_revision(root: Path, task_id: str) -> int:
    path = root.resolve() / ".cursor" / "task.md"
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise HarnessError(f"cannot read {path}: {exc}") from exc
    for line in lines:
        cells = [cell.strip() for cell in line.strip().strip("|").split("|")]
        if len(cells) < 7 or cells[1] != task_id:
            continue
        match = re.fullmatch(r"r(\d+)", cells[2])
        if not match:
            raise HarnessError(f"task {task_id} must bind a revision as rN")
        return int(match.group(1))
    raise HarnessError(f"task {task_id} is missing from .cursor/task.md")


def pause_request(root: Path) -> dict[str, Any] | None:
    path = harness_dir(root) / PAUSE_FILE
    if not path.exists():
        return None
    return read_json(path)


def request_pause(
    root: Path,
    *,
    reason: str,
    require_revision: bool = False,
    kind: str = "human",
) -> dict[str, Any]:
    if not reason.strip():
        raise HarnessError("pause reason is required")
    base = harness_dir(root)
    state_path = base / STATE_FILE
    if not state_path.exists():
        raise HarnessError("harness is not initialized")
    state = read_json(state_path)
    if not state.get("active"):
        raise HarnessError("harness is disabled")
    path = base / PAUSE_FILE
    existing = read_json(path) if path.exists() else {}
    if existing and kind == "goal_review":
        kind = str(existing.get("kind", kind))
        reason = str(existing.get("reason", reason))
    request = {
        "reason": reason,
        "kind": kind,
        "require_revision": bool(
            require_revision or existing.get("require_revision")
        ),
        "requested_at": existing.get("requested_at", utc_now()),
        "updated_at": utc_now(),
    }
    atomic_write_json(path, request)
    return request


def current_plan(
    root: Path,
    config: dict[str, Any],
) -> tuple[int | None, str | None]:
    plan_path = config.get("plan_doc") or config.get("feature_path")
    if not plan_path:
        return None, None
    return plan_metadata(root, str(plan_path))


def plan_can_run(
    root: Path,
    config: dict[str, Any],
    state: dict[str, Any],
) -> tuple[bool, str | None]:
    revision, review = current_plan(root, config)
    if revision is None:
        return True, None
    if review not in {"approved", "unreviewed"}:
        return False, f"plan review is {review}"
    if revision != state.get("plan_revision"):
        return (
            False,
            f"plan revision changed from {state.get('plan_revision')} to {revision}",
        )
    task_revision = task_plan_revision(root, str(state["task_id"]))
    if task_revision != revision:
        return (
            False,
            f"task {state['task_id']} binds r{task_revision}, plan is r{revision}",
        )
    return True, None


def resume(root: Path) -> dict[str, Any]:
    with state_lock(root):
        config, state = load_runtime(root)
        request = pause_request(root)
        if not request and state.get("phase") != "paused":
            raise HarnessError("runner is not paused")

        revision, review = current_plan(root, config)
        if request and request.get("require_revision"):
            if revision is None:
                raise HarnessError("this pause requires a plan document revision")
            if revision <= int(state.get("plan_revision") or 0):
                raise HarnessError(
                    "human correction requires Plan Revision to increase"
                )
        if revision is not None and review not in {"approved", "unreviewed"}:
            raise HarnessError(
                f"Plan Review must be approved or unreviewed, got {review}"
            )
        if revision is not None:
            task_revision = task_plan_revision(root, str(state["task_id"]))
            if task_revision != revision:
                raise HarnessError(
                    f"task {state['task_id']} binds r{task_revision}, "
                    f"plan is r{revision}"
                )

        try:
            if state.get("phase") != "paused":
                apply_event(state, Event.PAUSE_REQUESTED)
            apply_event(state, Event.PLAN_RESUMED)
        except TransitionError as exc:
            raise HarnessError(str(exc)) from exc
        state["plan_revision"] = revision
        state["plan_review"] = review
        state["current_run_id"] = None
        state["verified_fingerprint"] = None
        state["stop_report_requested"] = False
        state["actions_since_goal_review"] = 0
        state["last_goal_review_at"] = utc_now()
        state["updated_at"] = utc_now()
        atomic_write_json(harness_dir(root) / STATE_FILE, state)
        with contextlib.suppress(OSError):
            (harness_dir(root) / PAUSE_FILE).unlink()
        return state

