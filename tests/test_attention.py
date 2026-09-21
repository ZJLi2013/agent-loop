from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path

from harness.attention import record_goal_review
from harness.core import (
    HarnessError,
    completion_gate,
    initialize,
    load_runtime,
    run_command,
)
from harness.plan import pause_request


class AttentionRefreshTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def init(self, **kwargs: object) -> None:
        initialize(
            self.root,
            task_id="t1",
            verifier_argv=[sys.executable, "-c", "print('OK')"],
            **kwargs,
        )

    def run_pass(self) -> dict[str, object]:
        return run_command(
            self.root,
            [sys.executable, "-c", "print('step')"],
            kind="exec",
        )

    def test_action_count_pauses_until_goal_review_continues(self) -> None:
        self.init(goal_review_after_actions=2)
        self.run_pass()
        self.run_pass()
        _, state = load_runtime(self.root)

        self.assertEqual(state["phase"], "paused")
        self.assertEqual(pause_request(self.root)["kind"], "goal_review")
        self.assertIn("Goal Review", completion_gate(self.root) or "")
        with self.assertRaisesRegex(HarnessError, "runner is paused"):
            self.run_pass()

        state = record_goal_review(
            self.root,
            decision="continue",
            evidence="Goal unchanged; both steps advanced the current checkpoint.",
        )
        self.assertEqual(state["phase"], "ready")
        self.assertEqual(state["actions_since_goal_review"], 0)
        self.assertIsNone(pause_request(self.root))

    def test_failure_requires_goal_review(self) -> None:
        self.init()
        result = run_command(
            self.root,
            [sys.executable, "-c", "raise SystemExit(2)"],
            kind="exec",
        )
        _, state = load_runtime(self.root)

        self.assertEqual(result["outcome"], "fail")
        self.assertEqual(state["phase"], "paused")
        self.assertIn("goal_review_due", pause_request(self.root)["reason"])

    def test_elapsed_time_pauses_before_next_action(self) -> None:
        self.init(
            goal_review_after_actions=99,
            goal_review_after_seconds=0.1,
        )
        time.sleep(0.2)

        with self.assertRaisesRegex(HarnessError, "since review"):
            self.run_pass()
        self.assertEqual(pause_request(self.root)["kind"], "goal_review")

    def test_replan_turns_goal_review_into_revision_gate(self) -> None:
        self.init(goal_review_after_actions=1)
        self.run_pass()
        record_goal_review(
            self.root,
            decision="replan",
            evidence="Evidence contradicts the current next action.",
        )
        request = pause_request(self.root)

        self.assertEqual(request["kind"], "human")
        self.assertTrue(request["require_revision"])

    def test_stop_disables_the_loop(self) -> None:
        self.init(goal_review_after_actions=1)
        self.run_pass()
        state = record_goal_review(
            self.root,
            decision="stop",
            evidence="The Goal is no longer worth pursuing.",
        )

        self.assertFalse(state["active"])
        self.assertEqual(state["phase"], "stopped")
        self.assertIsNone(pause_request(self.root))


if __name__ == "__main__":
    unittest.main()

