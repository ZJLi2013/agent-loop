from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from harness.core import HarnessError, initialize, load_runtime, resume, run_command
from harness.plan import request_pause
from harness.plan_review import plan_review_record, run_plan_review


def reviewer_writing(
    report: dict[str, object] | str, *, modify_workspace: bool = False
) -> list[str]:
    text = report if isinstance(report, str) else json.dumps(report)
    modify = "Path('changed.py').write_text('changed = True\\n'); " if modify_workspace else ""
    code = (
        "from pathlib import Path; "
        "d=Path('.harness/plan-review'); "
        "c=d/'calls.txt'; "
        "c.write_text(str(int(c.read_text())+1) if c.exists() else '1'); "
        f"{modify}"
        f"(d/'report.json').write_text({text!r})"
    )
    return [sys.executable, "-c", code]


class PlanReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".agent-loop").mkdir()
        (self.root / ".agent-loop" / "task.md").write_text(
            "| P | id | rev | task | check | status | fail |\n"
            "|---|---|---|---|---|---|---|\n"
            "| P0 | t1 | r1 | first | check | 📝 proposed | 0 |\n",
            encoding="utf-8",
        )
        self.write_plan(1)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_plan(self, revision: int) -> None:
        (self.root / "plan.md").write_text(
            f"# Plan\n\nPlan Revision: {revision}\nPlan Review: proposed\n",
            encoding="utf-8",
        )

    def configure(self, argv: list[str]) -> None:
        (self.root / ".agent-loop" / "reviewer.json").write_text(
            json.dumps({"argv": argv, "timeout_seconds": 30}),
            encoding="utf-8",
        )

    def test_valid_report_is_cached_by_plan_revision(self) -> None:
        self.configure(
            reviewer_writing(
                {"verdict": "accept", "summary": "ready", "findings": []}
            )
        )

        first = run_plan_review(self.root, plan_doc="plan.md")
        second = run_plan_review(self.root, plan_doc="plan.md")

        self.assertEqual(first, second)
        self.assertEqual(first["verdict"], "accept")
        self.assertEqual(
            (self.root / ".harness" / "plan-review" / "calls.txt").read_text(),
            "1",
        )
        self.assertEqual(
            plan_review_record(self.root, "plan.md", 1)["summary"], "ready"
        )
        prompt = (self.root / ".harness" / "review" / "prompt.md").read_text(
            encoding="utf-8"
        )
        self.assertIn("领域先例", prompt)
        self.assertIn("本地设计文档", prompt)
        self.assertIn("交给被测方", prompt)
        self.assertIn("渲染样例", prompt)
        self.assertNotIn("review-checklist.md", prompt)

    def test_repo_checklist_is_listed_as_input(self) -> None:
        (self.root / ".agent-loop" / "review-checklist.md").write_text(
            "- item\n", encoding="utf-8"
        )
        self.configure(
            reviewer_writing(
                {"verdict": "accept", "summary": "ready", "findings": []}
            )
        )

        run_plan_review(self.root, plan_doc="plan.md")

        prompt = (self.root / ".harness" / "review" / "prompt.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(".agent-loop/review-checklist.md", prompt)

    def test_new_revision_runs_a_new_review(self) -> None:
        self.configure(
            reviewer_writing(
                {"verdict": "accept", "summary": "ready", "findings": []}
            )
        )
        run_plan_review(self.root, plan_doc="plan.md")
        self.write_plan(2)

        result = run_plan_review(self.root, plan_doc="plan.md")

        self.assertEqual(result["revision"], 2)
        self.assertEqual(
            (self.root / ".harness" / "plan-review" / "calls.txt").read_text(),
            "2",
        )
        self.assertIsNotNone(plan_review_record(self.root, "plan.md", 1))

    def test_invalid_report_is_persisted_as_incomplete(self) -> None:
        self.configure(reviewer_writing({"verdict": "revise", "summary": "bad"}))

        with self.assertRaisesRegex(HarnessError, "findings"):
            run_plan_review(self.root, plan_doc="plan.md")
        record = plan_review_record(self.root, "plan.md", 1)

        self.assertIn("findings", record["error"])
        with self.assertRaisesRegex(HarnessError, "incomplete"):
            run_plan_review(self.root, plan_doc="plan.md")

    def test_workspace_edits_invalidate_plan_review(self) -> None:
        self.configure(
            reviewer_writing(
                {"verdict": "accept", "summary": "ready", "findings": []},
                modify_workspace=True,
            )
        )

        with self.assertRaisesRegex(HarnessError, "modified the workspace"):
            run_plan_review(self.root, plan_doc="plan.md")

    def test_plan_review_requires_configured_reviewer(self) -> None:
        with self.assertRaisesRegex(HarnessError, "no reviewer configured"):
            run_plan_review(self.root, plan_doc="plan.md")

    def init(self) -> None:
        initialize(
            self.root,
            task_id="t1",
            plan_doc="plan.md",
            verifier_argv=[sys.executable, "-c", "print('OK')"],
        )

    def approve_plan(self, revision: int) -> None:
        (self.root / "plan.md").write_text(
            f"# Plan\n\nPlan Revision: {revision}\nPlan Review: approved\n",
            encoding="utf-8",
        )

    def write_task(self, revision: int) -> None:
        (self.root / ".agent-loop" / "task.md").write_text(
            "| P | id | rev | task | check | status | fail |\n"
            "|---|---|---|---|---|---|---|\n"
            f"| P0 | t1 | r{revision} | first | check | 🔬 doing | 0 |\n",
            encoding="utf-8",
        )

    def test_proposed_plan_is_reviewed_before_human_resume(self) -> None:
        self.configure(
            reviewer_writing(
                {"verdict": "accept", "summary": "ready", "findings": []}
            )
        )

        self.init()
        _, state = load_runtime(self.root)
        self.assertEqual(state["phase"], "paused")
        self.approve_plan(1)
        state = resume(self.root)

        self.assertEqual(state["phase"], "ready")
        self.assertEqual(
            (self.root / ".harness" / "plan-review" / "calls.txt").read_text(),
            "1",
        )

    def test_approved_plan_cannot_skip_missing_review(self) -> None:
        self.configure(
            reviewer_writing(
                {"verdict": "accept", "summary": "ready", "findings": []}
            )
        )
        self.approve_plan(1)

        with self.assertRaisesRegex(HarnessError, "set Plan Review to proposed"):
            self.init()

    def test_unattended_plan_is_reviewed_before_ready(self) -> None:
        self.configure(
            reviewer_writing(
                {"verdict": "accept", "summary": "ready", "findings": []}
            )
        )
        (self.root / "plan.md").write_text(
            "# Plan\n\nPlan Revision: 1\nPlan Review: unreviewed\n",
            encoding="utf-8",
        )

        self.init()
        _, state = load_runtime(self.root)

        self.assertEqual(state["phase"], "ready")
        self.assertIsNotNone(plan_review_record(self.root, "plan.md", 1))

    def test_revised_approved_plan_requires_review_then_reaffirmation(self) -> None:
        self.configure(
            reviewer_writing(
                {"verdict": "accept", "summary": "ready", "findings": []}
            )
        )
        self.init()
        self.approve_plan(1)
        resume(self.root)
        request_pause(self.root, reason="goal changed", require_revision=True)
        self.approve_plan(2)
        self.write_task(2)

        with self.assertRaisesRegex(HarnessError, "approve again"):
            resume(self.root)
        with self.assertRaisesRegex(HarnessError, "must be approved"):
            resume(self.root)
        self.approve_plan(2)
        state = resume(self.root)

        self.assertEqual(state["plan_revision"], 2)
        self.assertEqual(
            (self.root / ".harness" / "plan-review" / "calls.txt").read_text(),
            "2",
        )

    def test_missing_record_blocks_execution(self) -> None:
        self.configure(
            reviewer_writing(
                {"verdict": "accept", "summary": "ready", "findings": []}
            )
        )
        self.init()
        self.approve_plan(1)
        resume(self.root)
        record = next(
            path
            for path in (self.root / ".harness" / "plan-review").glob("*-r1.json")
        )
        record.unlink()

        with self.assertRaisesRegex(HarnessError, "no independent review"):
            run_command(
                self.root,
                [sys.executable, "-c", "print('must not run')"],
                kind="exec",
            )


if __name__ == "__main__":
    unittest.main()
