from __future__ import annotations

import json
import sys
import tempfile
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
from harness.review import run_review

TASKS = """| P | id | rev | task | check | status | fail |
|---|---|---|---|---|---|---|
| P0 | t1 | — | first | check | {status} | 0 |
| P0 | t2 | — | next | check | 📝 proposed | 0 |
"""


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
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
            **kwargs,
        )

    def run_pass(self) -> dict[str, object]:
        return run_command(
            self.root,
            [sys.executable, "-S", "-c", "print('step')"],
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

    def verified_with_reviewer(self, *, reviewed: bool) -> None:
        runtime = self.root / ".agent-loop"
        runtime.mkdir()
        (runtime / "task.md").write_text(
            TASKS.format(status="🔬 doing"), encoding="utf-8"
        )
        decision = {"decision": "continue", "next_task": "t2", "why": "next"}
        code = (
            "from pathlib import Path; "
            f"Path('.agent-loop/task.md').write_text({TASKS.format(status='✅ done')!r}, "
            "encoding='utf-8'); "
            f"Path('.harness/review/decision.json').write_text({json.dumps(decision)!r})"
        )
        (runtime / "reviewer.json").write_text(
            json.dumps({"argv": [sys.executable, "-S", "-c", code], "timeout_seconds": 30})
        )
        self.init(goal_review_after_actions=99)
        config, _ = load_runtime(self.root)
        run_command(self.root, list(config["verifier"]["argv"]), kind="verify")
        if reviewed:
            run_review(self.root)
        path = self.root / ".harness" / "state.json"
        state = json.loads(path.read_text(encoding="utf-8"))
        state["last_goal_review_at"] = "2000-01-01T00:00:00+00:00"
        path.write_text(json.dumps(state), encoding="utf-8")

    def test_gate_hands_off_reviewed_task_instead_of_goal_review(self) -> None:
        self.verified_with_reviewer(reviewed=True)

        followup = completion_gate(self.root) or ""
        _, state = load_runtime(self.root)

        self.assertIn("Reviewer chose continue -> t2", followup)
        self.assertIsNone(pause_request(self.root))
        self.assertEqual(state["phase"], "verified")

if __name__ == "__main__":
    unittest.main()
