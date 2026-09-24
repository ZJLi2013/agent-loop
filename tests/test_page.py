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
from harness.page import run_page
from harness.plan import pause_request
from harness.review import run_review

FAKE_PAGER = """
import json, sys
from pathlib import Path
args = sys.argv[1:]
with open("pager-calls.jsonl", "a", encoding="utf-8") as fh:
    fh.write(json.dumps(args) + "\\n")
if args[0] == "serve":
    reply = json.loads(Path("reply.json").read_text(encoding="utf-8"))
    print(json.dumps({"status": "command", "commands": [reply]}))
"""


def reviewer_writing(decision: dict[str, object]) -> list[str]:
    text = json.dumps(decision)
    code = (
        "from pathlib import Path; "
        f"Path('.harness/review/decision.json').write_text({text!r})"
    )
    return [sys.executable, "-c", code]


class PagerCheckpointTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        runtime = self.root / ".agent-loop"
        runtime.mkdir()
        (runtime / "task.md").write_text(
            "| P | id | rev | task | check | status | fail |\n"
            "| P0 | t1 | r1 | demo | check | 🔬 doing | 0 |\n",
            encoding="utf-8",
        )
        (self.root / "fake_pager.py").write_text(FAKE_PAGER, encoding="utf-8")
        (runtime / "pager.json").write_text(
            json.dumps(
                {
                    "argv": [sys.executable, "fake_pager.py"],
                    "project": "demo project",
                    "heartbeat_seconds": 0,
                }
            )
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_plan(self, revision: int, review: str) -> None:
        (self.root / "plan.md").write_text(
            f"# Demo\n\nPlan Revision: {revision}\nPlan Review: {review}\n\n"
            "## Goal\nDemo goal\n",
            encoding="utf-8",
        )

    def init(self, review: str = "approved", verifier: str = "print('OK')", **kw: object) -> None:
        self.write_plan(1, review)
        initialize(
            self.root,
            task_id="t1",
            plan_doc="plan.md",
            verifier_argv=[sys.executable, "-c", verifier],
            **kw,
        )

    def reply(self, verb: str, text: str = "") -> None:
        (self.root / "reply.json").write_text(
            json.dumps({"verb": verb, "task_id": "x", "text": text})
        )

    def calls(self) -> list[list[str]]:
        path = self.root / "pager-calls.jsonl"
        if not path.exists():
            return []
        return [json.loads(line) for line in path.read_text().splitlines()]

    def review_with(self, decision: dict[str, object]) -> None:
        (self.root / ".agent-loop" / "reviewer.json").write_text(
            json.dumps({"argv": reviewer_writing(decision)})
        )
        self.init()
        verify(self.root)
        run_review(self.root)

    def test_proposed_plan_is_paged_and_ok_approves_and_resumes(self) -> None:
        self.init(review="proposed")
        self.assertIn("plan_review", completion_gate(self.root) or "")

        self.reply("OK")
        outcome = run_page(self.root)

        send, serve = self.calls()
        self.assertEqual(send[0], "send")
        self.assertTrue(send[send.index("--task-id") + 1].startswith("demo-project.t1.plan_review."))
        self.assertEqual(send[send.index("--state") + 1], str(self.root / ".harness" / "pager-state.json"))
        self.assertEqual(serve[0], "serve")
        self.assertIn("Plan Review: approved", (self.root / "plan.md").read_text(encoding="utf-8"))
        _, state = load_runtime(self.root)
        self.assertEqual(state["phase"], "ready")
        self.assertEqual(outcome["reply"]["verb"], "OK")
        self.assertIn("not independently verified", completion_gate(self.root) or "")

    def test_do_on_ask_human_becomes_correction_then_revised_plan_is_paged(self) -> None:
        self.review_with({"decision": "ask_human", "why": "scope question"})
        self.assertIn("ask_human", completion_gate(self.root) or "")

        self.reply("DO", "switch to seeds 200-204")
        outcome = run_page(self.root)

        request = pause_request(self.root) or {}
        self.assertTrue(request.get("require_revision"))
        self.assertIn("switch to seeds 200-204", request.get("reason", ""))
        self.assertIn("switch to seeds 200-204", outcome["message"])
        self.assertIsNone(completion_gate(self.root))
        with self.assertRaisesRegex(HarnessError, "already paged"):
            run_page(self.root)

        self.write_plan(2, "proposed")
        self.assertIn("plan_review", completion_gate(self.root) or "")

    def test_reviewer_stop_only_notifies(self) -> None:
        self.review_with({"decision": "stop", "why": "goal reached"})
        self.assertIn("Notify the human", completion_gate(self.root) or "")

        run_page(self.root)

        self.assertEqual([call[0] for call in self.calls()], ["notify"])
        self.assertIsNone(completion_gate(self.root))

    def test_budget_exhaustion_is_paged_after_the_stop_report(self) -> None:
        self.init(verifier="raise SystemExit(1)", max_attempts=1)
        verify(self.root)
        self.assertIn("Auto-Stop Report", completion_gate(self.root) or "")
        self.assertIn("budget", completion_gate(self.root) or "")

        self.reply("STOP")
        outcome = run_page(self.root)

        self.assertIn("Stop at this checkpoint", outcome["message"])
        self.assertIsNone(completion_gate(self.root))
        with self.assertRaisesRegex(HarnessError, "already paged"):
            run_page(self.root)

    def test_without_pager_checkpoints_let_the_worker_stop(self) -> None:
        (self.root / ".agent-loop" / "pager.json").unlink()
        self.init(review="proposed")
        self.assertIsNone(completion_gate(self.root))
        with self.assertRaisesRegex(HarnessError, "no pager configured"):
            run_page(self.root)

    def test_invalid_pager_config_is_rejected_at_init(self) -> None:
        (self.root / ".agent-loop" / "pager.json").write_text('{"argv": []}')
        with self.assertRaisesRegex(HarnessError, "non-empty list"):
            self.init()


if __name__ == "__main__":
    unittest.main()
