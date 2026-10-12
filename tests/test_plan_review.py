from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

from harness import plan_review
from harness.core import HarnessError, initialize, load_runtime, resume, run_command
from harness.page import _plan_review_summary
from harness.plan import request_pause
from harness.plan_review import _review_key, plan_review_record, run_plan_review


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
        self.assertIn("设计文档显式链接的检查表", prompt)
        self.assertIn("`*-archive.md`", prompt)
        self.assertIn("不作判据", prompt)
        self.assertIn("其余文件不作证据", prompt)
        self.assertIn("够下结论就停止阅读", prompt)

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


REVISE = {"verdict": "revise", "summary": "tighten", "findings": ["seed blocks"]}
REVISE_STREAK = "plan review returned revise 3 times in a row"
NO_EXPERIMENT = "since the last exec/verify run"


class ReviewBrakeTest(unittest.TestCase):
    setUp = PlanReviewTest.setUp
    tearDown = PlanReviewTest.tearDown
    write_plan = PlanReviewTest.write_plan
    configure = PlanReviewTest.configure

    def record(
        self, revision: int, verdict: str | None, at: str, error: str | None = None
    ) -> None:
        directory = self.root / ".harness" / "plan-review"
        directory.mkdir(parents=True, exist_ok=True)
        (directory / f"{_review_key('plan.md', revision)}.json").write_text(
            json.dumps({
                "version": 1, "plan_doc": "plan.md", "revision": revision,
                "run_id": "x", "verdict": verdict, "summary": verdict,
                "findings": ["f"] if verdict == "revise" else [],
                "error": error, "at": at,
            }),
            encoding="utf-8",
        )

    def brake(self) -> list[str]:
        return plan_review.review_brake(self.root, "plan.md")

    def journal(self, kind: str, started_at: str) -> None:
        path = self.root / ".harness" / "runs.jsonl"
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"kind": kind, "started_at": started_at}) + "\n")

    def test_third_consecutive_revise_warns(self) -> None:
        self.record(1, "revise", "2026-10-12T06:00:00+00:00")
        self.record(2, "revise", "2026-10-12T06:05:00+00:00")
        self.assertFalse(any(REVISE_STREAK in w for w in self.brake()))
        self.write_plan(3)
        self.configure(reviewer_writing(REVISE))

        result = run_plan_review(self.root, plan_doc="plan.md")

        self.assertIn(f"{REVISE_STREAK} (r1–r3)", "\n".join(result["warnings"]))

    def test_accept_resets_streak_and_error_is_skipped(self) -> None:
        for revision, verdict in enumerate(["revise", "accept", "revise"], start=1):
            self.record(revision, verdict, f"2026-10-12T06:0{revision}:00+00:00")
        self.record(4, None, "2026-10-12T06:04:00+00:00", error="reviewer timeout")
        self.record(5, "revise", "2026-10-12T06:05:00+00:00")
        self.assertFalse(any(REVISE_STREAK in w for w in self.brake()))

        self.record(6, "revise", "2026-10-12T06:06:00+00:00")

        self.assertIn(f"{REVISE_STREAK} (r3–r6)", "\n".join(self.brake()))

    def test_revisions_since_last_experiment_warn_including_errors(self) -> None:
        self.journal("verify", "2026-10-11T04:53:39+00:00")
        self.record(1, "accept", "2026-10-11T04:32:32+00:00")
        self.record(2, None, "2026-10-12T06:33:43+00:00", error="workspace modified")
        self.record(3, "revise", "2026-10-12T06:43:58+00:00")
        self.record(4, "accept", "2026-10-12T06:48:14+00:00")

        self.assertIn(
            "3 plan revisions reviewed since the last exec/verify run (r2–r4); "
            "no new experiment evidence",
            self.brake(),
        )
        self.journal("exec", "2026-10-12T06:45:00+00:00")
        self.assertFalse(any(NO_EXPERIMENT in w for w in self.brake()))

    def test_cached_review_returns_warnings_without_storing_them(self) -> None:
        self.record(1, "revise", "2026-10-12T06:00:00+00:00")
        self.record(2, "revise", "2026-10-12T06:05:00+00:00")
        self.write_plan(3)
        self.configure(reviewer_writing(REVISE))

        first = run_plan_review(self.root, plan_doc="plan.md")
        second = run_plan_review(self.root, plan_doc="plan.md")

        self.assertEqual(first, second)
        self.assertTrue(any(REVISE_STREAK in w for w in second["warnings"]))
        self.assertNotIn("warnings", plan_review_record(self.root, "plan.md", 3))

    def test_plan_page_summary_includes_warnings(self) -> None:
        self.record(1, "revise", "2026-10-12T06:00:00+00:00")
        self.record(2, "revise", "2026-10-12T06:05:00+00:00")
        self.record(3, "revise", "2026-10-12T06:10:00+00:00")
        self.write_plan(3)

        summary = _plan_review_summary(self.root, {"plan_doc": "plan.md"})

        self.assertIn(REVISE_STREAK, summary)


if __name__ == "__main__":
    unittest.main()
