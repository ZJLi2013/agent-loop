from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from harness.core import (
    HarnessError,
    completion_gate,
    initialize,
    load_runtime,
    verify,
)
from harness.review import run_review

DECISION = ".harness/review/decision.json"


def reviewer_writing(decision: dict[str, object] | str) -> list[str]:
    text = decision if isinstance(decision, str) else json.dumps(decision)
    code = (
        "from pathlib import Path; "
        "Path('.agent-loop/task.md').write_text('rewritten by reviewer'); "
        f"Path({DECISION!r}).write_text({text!r})"
    )
    return [sys.executable, "-c", code]


class TaskBoundaryReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".agent-loop").mkdir()
        (self.root / ".agent-loop" / "task.md").write_text("| t1 |\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def init(self, argv: list[str] | None) -> None:
        if argv is not None:
            (self.root / ".agent-loop" / "reviewer.json").write_text(
                json.dumps({"argv": argv, "timeout_seconds": 30})
            )
        initialize(
            self.root,
            task_id="t1",
            verifier_argv=[sys.executable, "-c", "print('OK')"],
        )
        verify(self.root)

    def test_without_reviewer_verified_task_completes(self) -> None:
        self.init(None)
        self.assertIsNone(completion_gate(self.root))
        with self.assertRaisesRegex(HarnessError, "no reviewer configured"):
            run_review(self.root)

    def test_verified_task_requires_review_then_hands_off_next_task(self) -> None:
        self.init(reviewer_writing(
            {"decision": "continue", "next_task": "t2", "why": "next hypothesis"}
        ))
        self.assertIn("review", completion_gate(self.root) or "")

        outcome = run_review(self.root)
        prompt = (self.root / ".harness" / "review" / "prompt.md").read_text(
            encoding="utf-8"
        )

        self.assertEqual(outcome["review"]["decision"], "continue")
        self.assertIn("t1", prompt)
        self.assertIn(".agent-loop/task.md", prompt)
        followup = completion_gate(self.root) or ""
        self.assertIn("t2", followup)
        self.assertIn("--objection", followup)
        self.assertNotIn("stale", followup)

    def test_objection_reruns_reviewer_once(self) -> None:
        self.init(reviewer_writing(
            {"decision": "continue", "next_task": "t2", "why": "next hypothesis"}
        ))
        run_review(self.root)
        with self.assertRaisesRegex(HarnessError, "already reviewed"):
            run_review(self.root)

        run_review(self.root, objection="t2 was already done in t1")
        prompt = (self.root / ".harness" / "review" / "prompt.md").read_text(
            encoding="utf-8"
        )

        self.assertIn("t2 was already done in t1", prompt)
        self.assertNotIn("--objection", completion_gate(self.root) or "")
        with self.assertRaisesRegex(HarnessError, "attempts exhausted"):
            run_review(self.root, objection="again")

    def assert_worker_may_stop(self, decision: str) -> None:
        self.init(reviewer_writing({"decision": decision, "why": "done"}))
        run_review(self.root)
        self.assertIsNone(completion_gate(self.root))

    def test_stop_lets_the_worker_stop(self) -> None:
        self.assert_worker_may_stop("stop")

    def test_ask_human_lets_the_worker_stop(self) -> None:
        self.assert_worker_may_stop("ask_human")

    def test_invalid_decision_is_counted_then_reported_once(self) -> None:
        self.init(reviewer_writing({"decision": "continue", "why": "no task"}))

        first = run_review(self.root)
        self.assertIsNone(first["review"]["decision"])
        self.assertIn("continue requires next_task", completion_gate(self.root) or "")

        run_review(self.root)
        self.assertIn("report the reviewer error", completion_gate(self.root) or "")
        self.assertIsNone(completion_gate(self.root))
        _, state = load_runtime(self.root)
        self.assertEqual(state["review"]["attempts"], 2)

    def test_review_requires_fresh_verification(self) -> None:
        self.init(reviewer_writing({"decision": "stop", "why": "done"}))
        (self.root / "changed.py").write_text("changed = True\n")
        with self.assertRaisesRegex(HarnessError, "stale"):
            run_review(self.root)

    def test_invalid_reviewer_config_is_rejected_at_init(self) -> None:
        (self.root / ".agent-loop" / "reviewer.json").write_text('{"argv": []}')
        with self.assertRaisesRegex(HarnessError, "non-empty list"):
            initialize(
                self.root,
                task_id="t1",
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )


if __name__ == "__main__":
    unittest.main()
