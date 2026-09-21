from __future__ import annotations

from enum import Enum
from typing import Any


class Phase(str, Enum):
    PROPOSED = "proposed"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    VERIFYING = "verifying"
    VERIFIED = "verified"
    FAILED = "failed"
    STOPPED = "stopped"


class Event(str, Enum):
    PLAN_APPROVED = "plan_approved"
    RUN_STARTED = "run_started"
    RUN_FINISHED = "run_finished"
    RUN_FAILED = "run_failed"
    VERIFY_STARTED = "verify_started"
    VERIFY_PASSED = "verify_passed"
    VERIFY_FAILED = "verify_failed"
    PAUSE_REQUESTED = "pause_requested"
    PLAN_RESUMED = "plan_resumed"
    EVIDENCE_STALE = "evidence_stale"
    INTERRUPTED = "interrupted"
    BUDGET_EXHAUSTED = "budget_exhausted"
    DISABLED = "disabled"


ACTIVE = {
    Phase.PROPOSED,
    Phase.READY,
    Phase.RUNNING,
    Phase.PAUSED,
    Phase.VERIFYING,
    Phase.VERIFIED,
    Phase.FAILED,
}

TRANSITIONS: dict[Event, tuple[set[Phase], Phase]] = {
    Event.PLAN_APPROVED: ({Phase.PROPOSED, Phase.PAUSED}, Phase.READY),
    Event.RUN_STARTED: (
        {Phase.READY, Phase.FAILED, Phase.VERIFIED},
        Phase.RUNNING,
    ),
    Event.RUN_FINISHED: ({Phase.RUNNING}, Phase.READY),
    Event.RUN_FAILED: ({Phase.RUNNING}, Phase.FAILED),
    Event.VERIFY_STARTED: (
        {Phase.READY, Phase.FAILED, Phase.VERIFIED},
        Phase.VERIFYING,
    ),
    Event.VERIFY_PASSED: ({Phase.VERIFYING}, Phase.VERIFIED),
    Event.VERIFY_FAILED: ({Phase.VERIFYING}, Phase.FAILED),
    Event.PAUSE_REQUESTED: (ACTIVE - {Phase.STOPPED}, Phase.PAUSED),
    Event.PLAN_RESUMED: ({Phase.PAUSED, Phase.PROPOSED}, Phase.READY),
    Event.EVIDENCE_STALE: ({Phase.VERIFIED}, Phase.FAILED),
    Event.INTERRUPTED: ({Phase.RUNNING, Phase.VERIFYING}, Phase.FAILED),
    Event.BUDGET_EXHAUSTED: (ACTIVE, Phase.STOPPED),
    Event.DISABLED: (ACTIVE | {Phase.STOPPED}, Phase.STOPPED),
}


class TransitionError(ValueError):
    pass


def apply_event(state: dict[str, Any], event: Event) -> Phase:
    try:
        current = Phase(str(state["phase"]))
    except (KeyError, ValueError) as exc:
        raise TransitionError(f"invalid phase: {state.get('phase')}") from exc
    sources, target = TRANSITIONS[event]
    if current not in sources:
        raise TransitionError(f"{event.value} is invalid from {current.value}")
    state["phase"] = target.value
    return target

