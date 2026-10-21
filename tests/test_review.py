from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from harness.core import (
    HarnessError,
    completion_gate,
    initialize,
    load_runtime,
    run_command,
    verify,
)
from harness.plan_review import record_task_review
from harness.records import archive_closed_tasks, close_task
from harness.review import run_review

DECISION = ".harness/review/decision.json"
REWRITTEN_TASKS = """| P | id | rev | task | check | status | fail |
|---|---|---|---|---|---|---|
| P0 | t1 | — | first | check | ✅ done | 0 |
| P0 | t2 | — | next | check | 📝 proposed | 0 |
"""


def reviewer_writing(
    decision: dict[str, object] | str,
    tasks: str = REWRITTEN_TASKS,
) -> list[str]:
    text = decision if isinstance(decision, str) else json.dumps(decision)
    code = (
        "from pathlib import Path; "
        f"Path('.agent-loop/task.md').write_text({tasks!r}, encoding='utf-8'); "
        f"Path({DECISION!r}).write_text({text!r})"
    )
    return [sys.executable, "-S", "-c", code]


def reviewer_decision_only(decision: dict[str, object]) -> list[str]:
    text = json.dumps(decision)
    code = (
        "from pathlib import Path; "
        f"Path({DECISION!r}).write_text({text!r})"
    )
    return [sys.executable, "-S", "-c", code]


class TaskBoundaryReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".agent-loop").mkdir()
        (self.root / ".agent-loop" / "task.md").write_text(
            REWRITTEN_TASKS.replace("✅ done", "🔬 doing"),
            encoding="utf-8",
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def init(self, argv: list[str] | None, *, run_verifier: bool = True) -> None:
        if argv is not None:
            (self.root / ".agent-loop" / "reviewer.json").write_text(
                json.dumps({"argv": argv, "timeout_seconds": 30})
            )
        initialize(
            self.root,
            task_id="t1",
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
        )
        if run_verifier:
            config, _ = load_runtime(self.root)
            verifier = config["verifier"]
            run_command(
                self.root,
                list(verifier["argv"]),
                kind="verify",
                timeout_seconds=float(verifier["timeout_seconds"]),
            )

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
        self.assertIn("review 的单位是这个 verified task", prompt)
        self.assertIn("会改变 `continue / ask_human / stop`", prompt)
        self.assertIn("没有新 evidence 时不重新审查", prompt)
        self.assertIn("业界已有解法", prompt)
        self.assertIn("本地设计文档", prompt)
        self.assertIn("交给被测方", prompt)
        self.assertIn("实际产物与设计不一致", prompt)
        self.assertNotIn("review-checklist.md", prompt)
        self.assertIn("设计文档显式链接的检查表", prompt)
        self.assertIn("`*-archive.md`", prompt)
        self.assertIn("不作判据", prompt)
        self.assertIn("其余文件不作证据", prompt)
        self.assertIn("够下结论就停止阅读", prompt)
        followup = completion_gate(self.root) or ""
        self.assertIn("t2", followup)
        self.assertIn("--objection", followup)
        self.assertNotIn("stale", followup)

    def test_gate_reports_a_running_task_review(self) -> None:
        slow = reviewer_writing({"decision": "stop", "why": "done"})
        slow[-1] = "import time; time.sleep(2); " + slow[-1]
        self.init(slow)
        worker = threading.Thread(target=run_review, args=(self.root,))
        worker.start()
        deadline = time.monotonic() + 20
        while not load_runtime(self.root)[1].get("review_running"):
            self.assertLess(time.monotonic(), deadline)
            time.sleep(0.05)

        self.assertIn("is in progress", completion_gate(self.root) or "")
        with self.assertRaisesRegex(HarnessError, "is in progress"):
            run_review(self.root)
        with self.assertRaisesRegex(HarnessError, "task reviewer for t1 is running"):
            initialize(self.root, task_id="t2", verifier_argv=[sys.executable, "-S", "-c", "pass"])
        worker.join()

        self.assertEqual(load_runtime(self.root)[1]["review"]["decision"], "stop")

    def test_a_killed_task_review_does_not_block(self) -> None:
        self.init(reviewer_writing({"decision": "stop", "why": "done"}))
        gone = subprocess.Popen([sys.executable, "-S", "-c", "pass"])
        gone.wait()
        state_path = self.root / ".harness" / "state.json"
        state = json.loads(state_path.read_text())
        state["review_running"] = {"run_id": "rv-killed", "pid": gone.pid}
        state_path.write_text(json.dumps(state))

        self.assertIn("rv-killed lost its process", completion_gate(self.root) or "")
        run_review(self.root)
        self.assertEqual(load_runtime(self.root)[1]["review"]["decision"], "stop")

    def test_verify_automatically_runs_reviewer(self) -> None:
        self.init(
            reviewer_writing(
                {"decision": "continue", "next_task": "t2", "why": "next hypothesis"}
            ),
            run_verifier=False,
        )

        result = verify(self.root)
        _, state = load_runtime(self.root)

        self.assertEqual(result["automatic_review"]["decision"], "continue")
        self.assertEqual(state["review"]["next_task"], "t2")
        active = (self.root / ".agent-loop" / "task.md").read_text(encoding="utf-8")
        archive = (
            self.root / ".agent-loop" / "archive" / "tasks.md"
        ).read_text(encoding="utf-8")
        self.assertNotIn("| t1 |", active)
        self.assertIn("| t2 |", active)
        self.assertIn("| t1 |", archive)

    def test_pending_review_blocks_execution_and_next_task(self) -> None:
        self.init(
            reviewer_writing(
                {"decision": "continue", "next_task": "t2", "why": "next hypothesis"}
            )
        )

        with self.assertRaisesRegex(HarnessError, "awaiting reviewer decision"):
            run_command(
                self.root,
                [sys.executable, "-S", "-c", "print('must not run')"],
                kind="exec",
            )
        with self.assertRaisesRegex(HarnessError, "awaiting reviewer decision"):
            initialize(
                self.root,
                task_id="t2",
                verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
            )

    def test_init_takes_any_human_approved_task_not_only_the_reviewers_pick(self) -> None:
        self.init(
            reviewer_writing(
                {"decision": "continue", "next_task": "t2", "why": "next hypothesis"}
            ),
            run_verifier=False,
        )
        verify(self.root)
        with self.assertRaisesRegex(HarnessError, "approved as 🔬 doing"):
            initialize(
                self.root,
                task_id="t2",
                verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
            )
        task = self.root / ".agent-loop" / "task.md"
        task.write_text(
            task.read_text(encoding="utf-8")
            + "| P0 | t3 | — | human pick | check | 🔬 doing | 0 |\n",
            encoding="utf-8",
        )

        _, state = initialize(
            self.root,
            task_id="t3",
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
        )
        self.assertEqual(state["task_id"], "t3")

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

    def test_non_blocking_findings_reach_the_worker(self) -> None:
        self.init(
            reviewer_decision_only(
                {
                    "decision": "continue",
                    "next_task": "t2",
                    "why": "next",
                    "findings": [{"level": "suggest", "claim": "state snapshot not saved"}],
                }
            )
        )

        run_review(self.root)

        self.assertIn("Suggest: state snapshot not saved", completion_gate(self.root) or "")

CONTINUE = {"decision": "continue", "next_task": "t2", "why": "next hypothesis"}
PLAN_HEAD = "# Plan\n\nPlan Revision: 1\nPlan Review: unreviewed\n\n## 下一步决策\nt2\n"
PLAN_WITH_T1 = (
    PLAN_HEAD
    + '\n<a id="t1-design"></a>\n### t1 本地设计\ninput\n### t1 boundary review\nok\n'
    + "### t2 本地设计\nnext\n"
)
PLAN_MOVED = PLAN_HEAD + "\nt1 已归档：[plan-archive.md](plan-archive.md)\n### t2 本地设计\nnext\n"
PLAN_TASKS = REWRITTEN_TASKS.replace("| — |", "| r1 |")


def plan_reviewer(*calls: tuple[dict[str, object] | None, str, bool]) -> list[str]:
    accept = {"verdict": "accept", "findings": []}
    report = json.dumps({"summary": "ready", "tasks": {"t1": accept, "t2": accept}})
    code = "\n".join(
        [
            "import json, sys",
            "from pathlib import Path",
            "prompt = Path('.harness/review/prompt.md').read_text(encoding='utf-8')",
            "if not prompt.startswith('# Task boundary review'):",
            f"    Path('.harness/plan-review/report.json').write_text({report!r})",
            "    sys.exit(0)",
            "counter = Path('.harness/review/calls.txt')",
            "n = int(counter.read_text()) if counter.exists() else 0",
            "counter.write_text(str(n + 1))",
            f"decision, plan, fail = json.loads({json.dumps(calls)!r})[n]",
            f"Path('.agent-loop/task.md').write_text({PLAN_TASKS!r}, encoding='utf-8')",
            "Path('plan.md').write_text(plan, encoding='utf-8')",
            "if decision is not None:",
            f"    Path({DECISION!r}).write_text(json.dumps(decision))",
            "sys.exit(3 if fail else 0)",
        ]
    )
    return [sys.executable, "-S", "-c", code]


class ClosedPlanSectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".agent-loop").mkdir()
        (self.root / ".agent-loop" / "task.md").write_text(
            PLAN_TASKS.replace("✅ done", "🔬 doing"), encoding="utf-8"
        )
        (self.root / "plan.md").write_text(PLAN_WITH_T1, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def init(self, argv: list[str]) -> None:
        (self.root / ".agent-loop" / "reviewer.json").write_text(
            json.dumps({"argv": argv, "timeout_seconds": 30})
        )
        initialize(
            self.root,
            task_id="t1",
            plan_doc="plan.md",
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
        )
        run_command(
            self.root,
            [sys.executable, "-S", "-c", "print('OK')"],
            kind="verify",
            timeout_seconds=30,
        )

    def prompt(self) -> str:
        return (self.root / ".harness" / "review" / "prompt.md").read_text(
            encoding="utf-8"
        )

SUCCESSOR_TASKS = (
    "| P | id | rev | task | check | status | fail |\n"
    "|---|---|---|---|---|---|---|\n"
    "| P0 | t2 | r{revision} | next | check | 🔬 doing | 0 |\n"
)


class HumanSuccessorTest(unittest.TestCase):
    setUp = ClosedPlanSectionTest.setUp
    tearDown = ClosedPlanSectionTest.tearDown
    init = ClosedPlanSectionTest.init

    def review_as(self, decision: str, next_task: str | None = None) -> None:
        verdict = {"decision": decision, "why": "human decides"}
        if next_task:
            verdict["next_task"] = next_task
        self.init(plan_reviewer((verdict, PLAN_MOVED, False)))
        self.assertEqual(run_review(self.root)["review"]["decision"], decision)

    def human_decides(self, revision: int, review: str) -> None:
        plan = PLAN_MOVED.replace("Plan Revision: 1", f"Plan Revision: {revision}")
        (self.root / "plan.md").write_text(
            plan.replace("Plan Review: unreviewed", f"Plan Review: {review}"), encoding="utf-8"
        )
        (self.root / ".agent-loop" / "task.md").write_text(
            SUCCESSOR_TASKS.format(revision=revision), encoding="utf-8"
        )

    def init_successor(self) -> dict[str, object]:
        _, state = initialize(
            self.root,
            task_id="t2",
            plan_doc="plan.md",
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
        )
        return state

    def test_unattended_release_follows_the_reviewer(self) -> None:
        cases = (
            ("stop", None, False),
            ("ask_human", None, False),
            ("ask_human", "t2", True),
            ("continue", "t2", True),
        )
        for decision, next_task, starts in cases:
            with self.subTest(decision=decision, next_task=next_task):
                self.tearDown()
                self.setUp()
                self.review_as(decision, next_task)
                self.human_decides(1, "unreviewed")
                if starts:
                    self.assertEqual(self.init_successor()["task_id"], "t2")
                else:
                    with self.assertRaisesRegex(HarnessError, "unattended after"):
                        self.init_successor()

MAINLINE = (
    "## 主线\n\nOne line.\nMainline Review: {review}\n\n"
    "| Goal | 问题 | 退出条件 | 状态 | plan |\n|---|---|---|---|---|\n{rows}\n\n"
)
DONE_A = "| A | a | a | ✅ done | [plan](../plan.md) |"
DONE_SIDE = "| A | a | a | ✅ done | [plan](../side/plan.md) |"
NEXT_B = "| B | b | b | ▶ next | [plan](../next/plan.md) |"
TODO_C = "| C | c | c | ⬜ todo | |"
HANDOFF_TASKS = (
    "## Goal\n\n| P | id | rev | task | check | status | fail |\n|---|---|---|---|---|---|---|\n"
    "| P0 | {task} | r1 | next | check | 🔬 doing | 0 |\n"
)


class MainlineHandoffTest(unittest.TestCase):
    setUp = ClosedPlanSectionTest.setUp
    tearDown = ClosedPlanSectionTest.tearDown
    init = ClosedPlanSectionTest.init
    review_as = HumanSuccessorTest.review_as

    def start(
        self,
        rows: list[str] | None,
        *,
        review: str = "approved",
        task: str = "t2",
        plan: str = "next/plan.md",
    ) -> dict[str, object]:
        for name in ("next", "side"):
            (self.root / name).mkdir(exist_ok=True)
            (self.root / name / "plan.md").write_text(
                "# Next\n\nPlan Revision: 1\nPlan Review: unreviewed\n", encoding="utf-8"
            )
        mainline = MAINLINE.format(review=review, rows="\n".join(rows)) if rows else ""
        (self.root / ".agent-loop" / "task.md").write_text(
            mainline + HANDOFF_TASKS.format(task=task), encoding="utf-8"
        )
        _, state = initialize(
            self.root,
            task_id=task,
            plan_doc=plan,
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
        )
        return state

    def test_stop_hands_off_to_the_next_aligned_goal(self) -> None:
        self.review_as("stop")
        self.assertEqual(self.start([DONE_A, NEXT_B, TODO_C])["task_id"], "t2")

    def test_unapproved_mainline_stays_stopped(self) -> None:
        self.review_as("stop")
        with self.assertRaisesRegex(HarnessError, "unattended after"):
            self.start([DONE_A, NEXT_B], review="proposed")

    def test_skipped_goal_stays_stopped(self) -> None:
        self.review_as("stop")
        with self.assertRaisesRegex(HarnessError, "unattended after"):
            self.start([DONE_A, TODO_C, NEXT_B])

    def test_plan_outside_next_goal_stays_stopped(self) -> None:
        self.review_as("stop")
        with self.assertRaisesRegex(HarnessError, "unattended after"):
            self.start([DONE_A, NEXT_B], plan="side/plan.md")

    def test_handoff_still_needs_answered_plan_review(self) -> None:
        self.review_as("stop")
        must = {
            "level": "must", "claim": "wrong input", "consequence": "wasted run",
            "evidence": "plan:1", "change": "fix input", "human": False,
        }
        record_task_review(
            self.root, "t2", findings=[must], dropped=0, summary="", source="plan_review", run_id=None
        )
        with self.assertRaisesRegex(HarnessError, "must items"):
            self.start([DONE_A, NEXT_B])

    def test_without_mainline_stop_stays_stopped(self) -> None:
        self.review_as("stop")
        with self.assertRaisesRegex(HarnessError, "unattended after"):
            self.start(None)

    def test_within_goal_continue_keeps_the_named_task(self) -> None:
        self.review_as("continue", "t2")
        with self.assertRaisesRegex(HarnessError, "unattended after"):
            self.start([DONE_A, NEXT_B], task="t3", plan="plan.md")

    def test_side_goal_close_does_not_hand_off(self) -> None:
        self.review_as("stop")
        with self.assertRaisesRegex(HarnessError, "unattended after"):
            self.start([DONE_SIDE, NEXT_B])

    def test_archiving_keeps_mainline_rows(self) -> None:
        task_md = self.root / ".agent-loop" / "task.md"
        task_md.write_text(
            MAINLINE.format(review="approved", rows=DONE_A)
            + "| P | id | rev | task | check | status | fail |\n|---|---|---|---|---|---|---|\n"
            + "| P0 | t1 | r1 | first | check | ✅ done | 0 |\n",
            encoding="utf-8",
        )
        archive_closed_tasks(self.root)
        text = task_md.read_text(encoding="utf-8")
        self.assertIn(DONE_A, text)
        self.assertNotIn("| t1 |", text)

CLOSE_PLAN = (
    "# Plan\n\nPlan Revision: 1\nPlan Review: approved\n\n"
    "## 下一步决策\n见 [t1 设计](#t1-design)。\n\n"
    '<a id="t1-design"></a>\n### t1 本地设计\n输入见 [t2 设计](#t2-design)。\n\n'
    '<a id="t2-design"></a>\n### t2 本地设计\nnext\n'
)
CLOSE_TASKS = (
    "| P | id | rev | task | check | status | fail |\n"
    "|---|---|---|---|---|---|---|\n"
    "| P0 | t1 | r1 | 甲 | [设计](plan.md#t1-design)；通过 | 🔬 doing | 0 |\n"
    "| P0 | t2 | r1 | 乙 | [设计](plan.md#t2-design)；通过 | 📝 proposed | 0 |\n"
)


class CloseTaskTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / ".agent-loop"
        (self.runtime / "sub-exp").mkdir(parents=True)
        (self.runtime / "task.md").write_text(CLOSE_TASKS, encoding="utf-8")
        (self.runtime / "plan.md").write_text(CLOSE_PLAN, encoding="utf-8")
        (self.runtime / "sub-exp" / "x.md").write_text(
            "见 [t1 设计](../plan.md#t1-design)。\n", encoding="utf-8"
        )
        (self.runtime / "plan-archive.md").write_text(
            "### t0 boundary review\n\n下一步见 [t1](plan.md#t1-design)。\n", encoding="utf-8"
        )

    def tearDown(self) -> None:
        self.temp.cleanup()

    def section(self, doc: Path, target: str) -> str:
        name, _, anchor = target.partition("#")
        text = (doc.parent / name).read_text(encoding="utf-8") if name else doc.read_text(encoding="utf-8")
        start = text.index(f'<a id="{anchor}"></a>')
        end = text.find("<a id=", start + 1)
        return text[start:] if end < 0 else text[start:end]

    def test_harness_closes_task_moves_sections_and_keeps_links_resolving(self) -> None:
        self.assertIn("### t1 本地设计\n输入见", self.section(self.runtime / "plan.md", "#t1-design"))

        close_task(self.root, ".agent-loop/plan.md", "t1", "reviewed ok")

        plan = (self.runtime / "plan.md").read_text(encoding="utf-8")
        archive = (self.runtime / "plan-archive.md").read_text(encoding="utf-8")
        rows = (self.runtime / "archive" / "tasks.md").read_text(encoding="utf-8")
        other = (self.runtime / "sub-exp" / "x.md").read_text(encoding="utf-8")
        self.assertIn("| t1 | r1 | 甲 | [设计](../plan-archive.md#t1-design)；通过 | ✅ done |", rows)
        self.assertNotIn("### t1 本地设计", plan)
        self.assertIn("见 [t1 设计](plan-archive.md#t1-design)。", plan)
        self.assertIn("t1 的设计、结果与 review 依据见 [归档](plan-archive.md#t1-design)。", plan)
        self.assertIn("输入见 [t2 设计](plan.md#t2-design)。", archive)
        self.assertIn("### t1 boundary review\n\nreviewed ok", archive)
        self.assertIn("下一步见 [t1](#t1-design)。", archive)
        self.assertIn("[t1 设计](../plan-archive.md#t1-design)", other)
        for doc, target in (
            (self.runtime / "plan.md", "plan-archive.md#t1-design"),
            (self.runtime / "archive" / "tasks.md", "../plan-archive.md#t1-design"),
            (self.runtime / "sub-exp" / "x.md", "../plan-archive.md#t1-design"),
        ):
            self.assertIn("### t1 本地设计\n输入见", self.section(doc, target))
        self.assertIn('<a id="t2-design"></a>', self.section(self.runtime / "plan-archive.md", "plan.md#t2-design"))


if __name__ == "__main__":
    unittest.main()
