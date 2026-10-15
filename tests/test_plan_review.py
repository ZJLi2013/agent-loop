from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path

from harness.core import HarnessError, initialize, load_runtime, resume
from harness.plan_review import (
    approve_task,
    plan_review_ready,
    respond_task,
    review_status,
    run_plan_review,
    task_record,
)

MUST = {
    "level": "must",
    "claim": "two runners can hold the lock",
    "consequence": "state is written twice",
    "evidence": "harness/storage.py:66",
    "change": "re-read the holder before unlinking",
}
SUGGEST = {"level": "suggest", "claim": "name the test after the bug"}


def reviewer_writing(
    tasks: dict[str, list[dict[str, object]]] | str, *, modify_workspace: bool = False
) -> list[str]:
    report = tasks if isinstance(tasks, str) else json.dumps(
        {"summary": "ready", "tasks": {key: {"findings": value} for key, value in tasks.items()}}
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
    return [sys.executable, "-S", "-c", code]


class PlanReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".agent-loop").mkdir()
        self.write_tasks(("t1", "📝 proposed"))
        self.write_plan(1)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_plan(self, revision: int, review: str = "proposed", body: str = "alpha") -> None:
        (self.root / "plan.md").write_text(
            f"# Plan\n\nPlan Revision: {revision}\nPlan Review: {review}\n\n{body}\n",
            encoding="utf-8",
        )

    def write_tasks(self, *rows: tuple[str, str], revision: int = 1) -> None:
        (self.root / ".agent-loop" / "task.md").write_text(
            "| P | id | rev | task | check | status | fail |\n"
            "|---|---|---|---|---|---|---|\n"
            + "".join(
                f"| P0 | {task_id} | r{revision} | {task_id} 标题 | 通过 | {status} | 0 |\n"
                for task_id, status in rows
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
        return (self.root / ".harness" / "review" / "prompt.md").read_text(encoding="utf-8")

    def review(self) -> dict[str, object]:
        return run_plan_review(self.root, plan_doc="plan.md")

    def init(self, task_id: str = "t1") -> dict[str, object]:
        _, state = initialize(
            self.root,
            task_id=task_id,
            plan_doc="plan.md",
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
        )
        return state

    def test_review_runs_once_and_prompt_keeps_contract(self) -> None:
        self.configure(reviewer_writing({"t1": []}))

        self.review()
        second = self.review()
        prompt = self.prompt()

        self.assertEqual(second["tasks"], {})
        self.assertEqual(self.calls(), "1")
        self.assertIn("- t1：t1 标题", prompt)
        for text in (
            "领域先例", "本地设计文档", "交给被测方", "渲染样例", "设计文档显式链接的检查表",
            "`*-archive.md`", "不作判据", "其余文件不作证据", "够下结论就停止阅读",
            "被忽略时会让方向错", "各最多 3 条", "不要求补证",
        ):
            self.assertIn(text, prompt)
        self.assertNotIn("review-checklist.md", prompt)

    def test_new_task_is_reviewed_alone(self) -> None:
        self.configure(reviewer_writing({"t1": [], "t2": []}))
        self.review()
        self.write_tasks(("t1", "⬜ todo"), ("t2", "📝 proposed"))

        result = self.review()

        self.assertEqual(sorted(result["tasks"]), ["t2"])
        self.assertNotIn("- t1：", self.prompt())

    def test_design_changes_after_review_do_not_trigger_another_review(self) -> None:
        self.configure(reviewer_writing({"t1": [MUST]}))
        self.review()
        self.write_plan(2, body="alpha, with the must item applied")
        self.write_tasks(("t1", "🔬 doing"), revision=2)

        self.assertEqual(self.review()["tasks"], {})
        self.assertEqual(self.calls(), "1")

    def test_items_over_the_limit_are_dropped(self) -> None:
        self.configure(reviewer_writing({"t1": [MUST] * 4 + [SUGGEST] * 4}))

        self.review()
        last = task_record(self.root, "t1")["reviews"][-1]

        self.assertEqual([item["level"] for item in last["findings"]], ["must"] * 3 + ["suggest"] * 3)
        self.assertEqual(last["dropped"], 2)

    def test_must_items_need_an_answer_before_init(self) -> None:
        self.configure(reviewer_writing({"t1": [MUST, SUGGEST]}))
        self.write_plan(1, review="unreviewed")

        with self.assertRaisesRegex(HarnessError, "must items 1 .*--respond t1"):
            self.init()
        respond_task(self.root, "t1", items=["1=applied"])
        state = self.init()

        self.assertEqual(state["phase"], "ready")
        self.assertEqual(self.calls(), "1")

    def test_answers_follow_the_protocol(self) -> None:
        self.configure(reviewer_writing({"t1": [MUST, SUGGEST]}))
        self.review()

        with self.assertRaisesRegex(HarnessError, "not skipped"):
            respond_task(self.root, "t1", items=["1=skipped"])
        with self.assertRaisesRegex(HarnessError, "reject requires --reason"):
            respond_task(self.root, "t1", items=["1=reject"])
        respond_task(self.root, "t1", items=["1=reject"], reason="the lock is per process")
        with self.assertRaisesRegex(HarnessError, "already answered"):
            respond_task(self.root, "t1", items=["1=applied"])
        with self.assertRaisesRegex(HarnessError, "no reviewer item 3"):
            respond_task(self.root, "t1", items=["3=applied"])

        self.assertTrue(plan_review_ready(self.root, "t1")[0])

    def test_human_items_wait_for_the_human(self) -> None:
        human = {**MUST, "human": True}
        self.configure(reviewer_writing({"t1": [human], "t2": []}))
        self.write_tasks(("t1", "📝 proposed"), ("t2", "📝 proposed"))
        self.review()
        respond_task(self.root, "t1", items=["1=applied"])

        ready, reason = plan_review_ready(self.root, "t1")
        self.assertFalse(ready)
        self.assertIn("--approve t1", reason or "")
        self.assertTrue(plan_review_ready(self.root, "t2")[0])

        approve_task(self.root, "t1", reason="选方案 A")
        self.assertTrue(plan_review_ready(self.root, "t1", review="approved")[0])
        with self.assertRaisesRegex(HarnessError, "human decision"):
            plan_review_ready(self.root, "t1", review="unreviewed")

    def test_cli_respond_approve_and_again(self) -> None:
        from harness.run import main

        self.configure(reviewer_writing({"t1": [MUST]}))
        self.review()
        base = ["--root", str(self.root), "plan-review", "--plan-doc", "plan.md"]

        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(main([*base, "--respond", "t1", "--item", "1=applied"]), 0)
            self.assertEqual(main([*base, "--approve", "t1", "--reason", "批"]), 0)
            self.assertEqual(main([*base, "--again", "t1", "--reason", "再审"]), 0)
        self.assertEqual(review_status(self.root, "t1"), "needs_review")
        for argv in (
            [*base, "--reason", "x"],
            [*base, "--respond", "t1"],
            [*base, "--item", "1=applied"],
            [*base, "--approve", "t1", "--again", "t1"],
        ):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                main(argv)

    def test_proposed_plan_is_reviewed_before_human_resume(self) -> None:
        self.configure(reviewer_writing({"t1": []}))

        self.init()
        self.assertEqual(load_runtime(self.root)[1]["phase"], "paused")
        self.write_plan(1, review="approved")
        state = resume(self.root)

        self.assertEqual(state["phase"], "ready")
        self.assertEqual(self.calls(), "1")

    def test_approved_plan_cannot_skip_missing_review(self) -> None:
        self.configure(reviewer_writing({"t1": []}))
        self.write_plan(1, review="approved")

        with self.assertRaisesRegex(HarnessError, "set Plan Review to proposed"):
            self.init()

    def test_records_from_before_the_protocol_still_read(self) -> None:
        path = self.root / ".harness" / "plan-review" / "tasks" / "t1.json"
        path.parent.mkdir(parents=True)
        path.write_text(json.dumps({
            "task_id": "t1",
            "reviews": [{"digest": "x", "verdict": "revise", "findings": ["seed blocks"],
                         "summary": "s", "source": "plan_review", "run_id": "r", "at": "2026-10-15T00:00:00+00:00"}],
            "approvals": [],
            "again": [],
        }), encoding="utf-8")

        self.assertTrue(plan_review_ready(self.root, "t1")[0])
        self.assertEqual(task_record(self.root, "t1")["reviews"][0]["findings"][0]["level"], "suggest")

if __name__ == "__main__":
    unittest.main()
