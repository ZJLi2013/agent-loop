from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from harness.core import HarnessError, initialize, load_runtime, resume, run_command
from harness.plan import request_pause
from harness.plan_review import (
    again_task,
    approve_task,
    plan_review_ready,
    review_status,
    run_plan_review,
)
from harness.records import task_digest

ACCEPT = {"verdict": "accept", "findings": []}
REVISE = {"verdict": "revise", "findings": ["seed blocks"]}


def reviewer_writing(
    tasks: dict[str, dict[str, object]] | str, *, modify_workspace: bool = False
) -> list[str]:
    report = tasks if isinstance(tasks, str) else json.dumps(
        {"summary": "ready", "tasks": tasks}
    )
    modify = "Path('changed.py').write_text('changed = True\\n'); " if modify_workspace else ""
    code = (
        "from pathlib import Path; "
        "d=Path('.harness/plan-review'); "
        "c=d/'calls.txt'; "
        "c.write_text(str(int(c.read_text())+1) if c.exists() else '1'); "
        f"{modify}"
        f"(d/'report.json').write_text({report!r})"
    )
    return [sys.executable, "-c", code]


class PlanReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".agent-loop").mkdir()
        self.write_tasks(("t1", "a", "📝 proposed"))
        self.write_plan(1)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_plan(
        self, revision: int, review: str = "proposed", a: str = "alpha", b: str = "beta"
    ) -> None:
        (self.root / "plan.md").write_text(
            f"# Plan\n\nPlan Revision: {revision}\nPlan Review: {review}\n\n"
            f'<a id="a"></a>\n### a 设计\n甲的做法：{a}。\n\n'
            f'<a id="b"></a>\n### b 设计\n乙的做法：{b}。\n',
            encoding="utf-8",
        )

    def write_tasks(self, *rows: tuple[str, str, str], revision: int = 1) -> None:
        (self.root / ".agent-loop" / "task.md").write_text(
            "| P | id | rev | task | check | status | fail |\n"
            "|---|---|---|---|---|---|---|\n"
            + "".join(
                f"| P0 | {task_id} | r{revision} | {task_id} 标题 | "
                f"[设计](../plan.md#{anchor})；通过 | {status} | 0 |\n"
                for task_id, anchor, status in rows
            ),
            encoding="utf-8",
        )

    def configure(self, argv: list[str]) -> None:
        (self.root / ".agent-loop" / "reviewer.json").write_text(
            json.dumps({"argv": argv, "timeout_seconds": 30}), encoding="utf-8"
        )

    def calls(self) -> str:
        path = self.root / ".harness" / "plan-review" / "calls.txt"
        return path.read_text() if path.exists() else "0"

    def prompt(self) -> str:
        return (self.root / ".harness" / "review" / "prompt.md").read_text(
            encoding="utf-8"
        )

    def review(self) -> dict[str, object]:
        return run_plan_review(self.root, plan_doc="plan.md")

    def init(self, task_id: str = "t1") -> dict[str, object]:
        _, state = initialize(
            self.root,
            task_id=task_id,
            plan_doc="plan.md",
            verifier_argv=[sys.executable, "-c", "print('OK')"],
        )
        return state

    def test_review_is_cached_per_task_and_prompt_keeps_contract(self) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT}))

        first = self.review()
        second = self.review()
        prompt = self.prompt()

        self.assertEqual(first["tasks"]["t1"]["verdict"], "accept")
        self.assertEqual(second["tasks"], {})
        self.assertEqual(self.calls(), "1")
        self.assertEqual(review_status(self.root, "t1")[0], "reviewed")
        self.assertIn("- t1：t1 标题", prompt)
        for text in (
            "领域先例", "本地设计文档", "交给被测方", "渲染样例", "设计文档显式链接的检查表",
            "`*-archive.md`", "不作判据", "其余文件不作证据", "够下结论就停止阅读",
        ):
            self.assertIn(text, prompt)
        self.assertNotIn("review-checklist.md", prompt)

    def test_repo_checklist_is_listed_as_input(self) -> None:
        (self.root / ".agent-loop" / "review-checklist.md").write_text(
            "- item\n", encoding="utf-8"
        )
        self.configure(reviewer_writing({"t1": ACCEPT}))

        self.review()

        self.assertIn(".agent-loop/review-checklist.md", self.prompt())

    def test_new_task_is_reviewed_alone(self) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT, "t2": ACCEPT}))
        self.review()
        self.write_tasks(("t1", "a", "⬜ todo"), ("t2", "b", "📝 proposed"))

        result = self.review()

        self.assertEqual(sorted(result["tasks"]), ["t2"])
        self.assertIn("- t2：", self.prompt())
        self.assertNotIn("- t1：", self.prompt())
        self.assertEqual(self.calls(), "2")

    def test_revised_task_is_reviewed_alone(self) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT, "t2": ACCEPT}))
        self.write_tasks(("t1", "a", "📝 proposed"), ("t2", "b", "⬜ todo"))
        self.review()
        self.write_plan(1, a="alpha2")
        self.write_tasks(("t1", "a", "📝 proposed"), ("t2", "b", "📝 proposed"))

        result = self.review()

        self.assertEqual(sorted(result["tasks"]), ["t1"])
        self.assertNotIn("- t2：", self.prompt())

    def test_metadata_edits_keep_the_review(self) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT, "t2": ACCEPT}))
        self.write_tasks(("t1", "a", "📝 proposed"), ("t2", "b", "📝 proposed"))
        self.review()
        before = (task_digest(self.root, "t1"), task_digest(self.root, "t2"))

        self.write_plan(7)
        self.write_tasks(("t2", "b", "⬜ todo"), ("t1", "a", "🔬 doing"), revision=7)
        result = self.review()

        self.assertEqual((task_digest(self.root, "t1"), task_digest(self.root, "t2")), before)
        self.assertEqual(result["tasks"], {})
        self.assertEqual(self.calls(), "1")

    def test_design_sections_are_digested_separately(self) -> None:
        self.write_tasks(("t1", "a", "📝 proposed"), ("t2", "b", "📝 proposed"))
        before = (task_digest(self.root, "t1"), task_digest(self.root, "t2"))

        self.write_plan(1, a="alpha2")

        self.assertNotEqual(task_digest(self.root, "t1"), before[0])
        self.assertEqual(task_digest(self.root, "t2"), before[1])

    def test_report_missing_a_requested_task_is_invalid_and_not_cached(self) -> None:
        self.write_tasks(("t1", "a", "📝 proposed"), ("t2", "b", "📝 proposed"))
        self.configure(reviewer_writing({"t1": ACCEPT}))

        with self.assertRaisesRegex(HarnessError, "t2"):
            self.review()
        with self.assertRaisesRegex(HarnessError, "t2"):
            self.review()

        self.assertEqual(self.calls(), "2")
        self.assertEqual(review_status(self.root, "t1")[0], "needs_review")

    def test_revise_without_findings_is_invalid(self) -> None:
        self.configure(reviewer_writing({"t1": {"verdict": "revise", "findings": []}}))

        with self.assertRaisesRegex(HarnessError, "at least one finding"):
            self.review()

    def test_workspace_edits_invalidate_plan_review(self) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT}, modify_workspace=True))

        with self.assertRaisesRegex(HarnessError, "modified the workspace"):
            self.review()

    def test_plan_review_requires_configured_reviewer(self) -> None:
        with self.assertRaisesRegex(HarnessError, "no reviewer configured"):
            self.review()

    def test_revise_goes_to_the_human(self) -> None:
        self.configure(reviewer_writing({"t1": REVISE}))
        self.review()
        self.write_plan(1, a="alpha2")

        result = self.review()
        ready, reason = plan_review_ready(self.root, "t1")

        self.assertEqual(result["waiting"], ["t1"])
        self.assertEqual(self.calls(), "1")
        self.assertFalse(ready)
        self.assertIn("--approve t1", reason or "")
        self.assertIn("--again t1", reason or "")

        again_task(self.root, "t1", reason="再审一次")
        self.review()
        self.write_plan(1, a="alpha3")

        self.assertEqual(self.calls(), "2")
        self.assertEqual(self.review()["waiting"], ["t1"])

    def test_human_approval_binds_to_the_digest(self) -> None:
        self.configure(reviewer_writing({"t1": REVISE}))
        self.review()
        self.write_plan(1, review="approved", a="alpha with notes")
        self.write_tasks(("t1", "a", "🔬 doing"))

        approve_task(self.root, "t1", reason="按意见改完就批")
        state = self.init()

        self.assertEqual(state["phase"], "ready")
        self.assertEqual(self.calls(), "1")
        self.write_plan(1, review="approved", a="changed again")
        self.assertEqual(review_status(self.root, "t1")[0], "needs_review")

    def test_approval_needs_a_first_review_and_a_reason(self) -> None:
        with self.assertRaisesRegex(HarnessError, "never been reviewed"):
            approve_task(self.root, "t1", reason="直接批")
        self.configure(reviewer_writing({"t1": REVISE}))
        self.review()
        with self.assertRaisesRegex(HarnessError, "--reason"):
            approve_task(self.root, "t1", reason="  ")
        with self.assertRaisesRegex(HarnessError, "does not need"):
            again_task(self.root, "t1", reason="再审")

    def test_unreviewed_self_approval_cannot_use_a_human_approval(self) -> None:
        self.configure(reviewer_writing({"t1": REVISE}))
        self.review()
        self.write_plan(1, review="unreviewed", a="alpha2")
        self.write_tasks(("t1", "a", "🔬 doing"))
        approve_task(self.root, "t1", reason="批")

        with self.assertRaisesRegex(HarnessError, "human approval"):
            self.init()

    def test_approval_is_journaled_with_reason(self) -> None:
        self.configure(reviewer_writing({"t1": REVISE}))
        self.review()

        approve_task(self.root, "t1", reason="批准，调整 review 门槛")
        entry = json.loads(
            (self.root / ".harness" / "runs.jsonl").read_text(encoding="utf-8").splitlines()[-1]
        )
        result = json.loads(
            (self.root / ".harness" / "artifacts" / entry["run_id"] / "result.json").read_text(
                encoding="utf-8"
            )
        )

        self.assertEqual((entry["kind"], entry["task_id"]), ("plan_review_approval", "t1"))
        self.assertEqual(result["reason"], "批准，调整 review 门槛")

    def test_cli_approve_and_again(self) -> None:
        from harness.run import main

        self.configure(reviewer_writing({"t1": REVISE}))
        self.review()
        self.write_plan(1, a="alpha2")
        base = ["--root", str(self.root), "plan-review", "--plan-doc", "plan.md"]

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([*base, "--again", "t1", "--reason", "再审"]), 0)
            self.assertEqual(main([*base, "--approve", "t1", "--reason", "批"]), 0)
        self.assertEqual(review_status(self.root, "t1")[0], "approved")
        for argv in ([*base, "--reason", "x"], [*base, "--approve", "t1", "--again", "t1"]):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(argv)

    def test_proposed_plan_is_reviewed_before_human_resume(self) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT}))

        self.init()
        _, state = load_runtime(self.root)
        self.assertEqual(state["phase"], "paused")
        self.write_plan(1, review="approved")
        state = resume(self.root)

        self.assertEqual(state["phase"], "ready")
        self.assertEqual(self.calls(), "1")

    def test_approved_plan_cannot_skip_missing_review(self) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT}))
        self.write_plan(1, review="approved")

        with self.assertRaisesRegex(HarnessError, "set Plan Review to proposed"):
            self.init()

    def test_unattended_plan_is_reviewed_before_ready(self) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT}))
        self.write_plan(1, review="unreviewed")

        state = self.init()

        self.assertEqual(state["phase"], "ready")
        self.assertEqual(review_status(self.root, "t1")[0], "reviewed")

    def correct_plan(self, **design: str) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT}))
        self.init()
        self.write_plan(1, review="approved")
        resume(self.root)
        request_pause(self.root, reason="goal changed", require_revision=True)
        self.write_plan(2, review="approved", **design)
        self.write_tasks(("t1", "a", "🔬 doing"), revision=2)

    def test_changed_design_after_approval_requires_review_then_reaffirmation(self) -> None:
        self.correct_plan(a="alpha2")

        with self.assertRaisesRegex(HarnessError, "approve again"):
            resume(self.root)
        self.write_plan(2, review="approved", a="alpha2")
        state = resume(self.root)

        self.assertEqual(state["plan_revision"], 2)
        self.assertEqual(self.calls(), "2")

    def test_metadata_only_correction_resumes_without_review(self) -> None:
        self.correct_plan()

        state = resume(self.root)

        self.assertEqual(state["plan_revision"], 2)
        self.assertEqual(self.calls(), "1")

    def test_results_written_into_the_design_after_init_do_not_block_execution(self) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT}))
        self.write_plan(1, review="unreviewed")
        self.init()
        self.write_plan(1, review="unreviewed", a="alpha。结果：通过")

        result = run_command(self.root, [sys.executable, "-c", "print('ok')"], kind="exec")

        self.assertEqual(result["outcome"], "pass")
        self.assertEqual(self.calls(), "1")

    def test_resume_after_a_plain_pause_keeps_the_admitted_design(self) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT}))
        self.init()
        self.write_plan(1, review="approved")
        resume(self.root)
        self.write_plan(1, review="approved", a="alpha。结果：通过")
        request_pause(self.root, reason="check in")

        state = resume(self.root)

        self.assertEqual(state["phase"], "ready")
        self.assertEqual(self.calls(), "1")

    def test_missing_record_blocks_execution(self) -> None:
        self.configure(reviewer_writing({"t1": ACCEPT}))
        self.init()
        self.write_plan(1, review="approved")
        resume(self.root)
        (self.root / ".harness" / "plan-review" / "tasks" / "t1.json").unlink()

        with self.assertRaisesRegex(HarnessError, "no independent review"):
            run_command(
                self.root,
                [sys.executable, "-c", "print('must not run')"],
                kind="exec",
            )


if __name__ == "__main__":
    unittest.main()
