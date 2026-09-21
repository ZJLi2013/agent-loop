from __future__ import annotations

import unittest

from harness.protocol import Event, Phase, TransitionError, apply_event


class ProtocolTest(unittest.TestCase):
    def assert_transition(
        self,
        source: Phase,
        event: Event,
        target: Phase,
    ) -> None:
        state = {"phase": source.value}
        self.assertEqual(apply_event(state, event), target)
        self.assertEqual(state["phase"], target.value)

    def test_happy_path(self) -> None:
        self.assert_transition(
            Phase.PROPOSED, Event.PLAN_APPROVED, Phase.READY
        )
        self.assert_transition(Phase.READY, Event.RUN_STARTED, Phase.RUNNING)
        self.assert_transition(
            Phase.RUNNING, Event.RUN_FINISHED, Phase.READY
        )
        self.assert_transition(
            Phase.READY, Event.VERIFY_STARTED, Phase.VERIFYING
        )
        self.assert_transition(
            Phase.VERIFYING, Event.VERIFY_PASSED, Phase.VERIFIED
        )

    def test_pause_resume_and_stale_evidence(self) -> None:
        self.assert_transition(
            Phase.RUNNING, Event.PAUSE_REQUESTED, Phase.PAUSED
        )
        self.assert_transition(
            Phase.PAUSED, Event.PLAN_RESUMED, Phase.READY
        )
        self.assert_transition(
            Phase.VERIFIED, Event.EVIDENCE_STALE, Phase.FAILED
        )

    def test_budget_and_disable_stop_active_states(self) -> None:
        for phase in (Phase.READY, Phase.RUNNING, Phase.PAUSED, Phase.FAILED):
            self.assert_transition(
                phase, Event.BUDGET_EXHAUSTED, Phase.STOPPED
            )

    def test_invalid_transition_is_rejected(self) -> None:
        with self.assertRaisesRegex(
            TransitionError, "verify_passed is invalid from ready"
        ):
            apply_event({"phase": "ready"}, Event.VERIFY_PASSED)


if __name__ == "__main__":
    unittest.main()

