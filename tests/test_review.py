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
    run_command,
    verify,
)
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
    return [sys.executable, "-c", code]


def reviewer_decision_only(decision: dict[str, object]) -> list[str]:
    text = json.dumps(decision)
    code = (
        "from pathlib import Path; "
        f"Path({DECISION!r}).write_text({text!r})"
    )
    return [sys.executable, "-c", code]


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
            verifier_argv=[sys.executable, "-c", "print('OK')"],
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
        followup = completion_gate(self.root) or ""
        self.assertIn("t2", followup)
        self.assertIn("--objection", followup)
        self.assertNotIn("stale", followup)

    def test_repo_checklist_is_listed_as_input(self) -> None:
        (self.root / ".agent-loop" / "review-checklist.md").write_text(
            "- item\n", encoding="utf-8"
        )
        self.init(reviewer_writing(
            {"decision": "continue", "next_task": "t2", "why": "next hypothesis"}
        ))

        run_review(self.root)

        prompt = (self.root / ".harness" / "review" / "prompt.md").read_text(
            encoding="utf-8"
        )
        self.assertIn(".agent-loop/review-checklist.md", prompt)

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
                [sys.executable, "-c", "print('must not run')"],
                kind="exec",
            )
        with self.assertRaisesRegex(HarnessError, "awaiting reviewer decision"):
            initialize(
                self.root,
                task_id="t2",
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )

    def test_review_allows_only_the_selected_next_task(self) -> None:
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
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )
        task = self.root / ".agent-loop" / "task.md"
        task.write_text(
            task.read_text(encoding="utf-8").replace("📝 proposed", "🔬 doing"),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(HarnessError, "selected t2, not t3"):
            initialize(
                self.root,
                task_id="t3",
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )
        _, state = initialize(
            self.root,
            task_id="t2",
            verifier_argv=[sys.executable, "-c", "print('OK')"],
        )
        self.assertEqual(state["task_id"], "t2")

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

    def test_review_requires_current_task_to_close(self) -> None:
        self.init(
            reviewer_decision_only(
                {"decision": "continue", "next_task": "t2", "why": "next"}
            )
        )

        outcome = run_review(self.root)

        self.assertIsNone(outcome["review"]["decision"])
        self.assertIn("must mark task t1", outcome["review"]["error"])

    def test_continue_requires_proposed_successor(self) -> None:
        decision = {
            "decision": "continue",
            "next_task": "t2",
            "why": "next",
        }
        todo_successor = REWRITTEN_TASKS.replace("📝 proposed", "⬜ todo")
        self.init(reviewer_writing(decision, todo_successor))

        outcome = run_review(self.root)

        self.assertIsNone(outcome["review"]["decision"])
        self.assertIn("must be 📝 proposed", outcome["review"]["error"])

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
    report = json.dumps({"verdict": "accept", "summary": "ready", "findings": []})
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
    return [sys.executable, "-c", code]


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
            verifier_argv=[sys.executable, "-c", "print('OK')"],
        )
        run_command(
            self.root,
            [sys.executable, "-c", "print('OK')"],
            kind="verify",
            timeout_seconds=30,
        )

    def prompt(self) -> str:
        return (self.root / ".harness" / "review" / "prompt.md").read_text(
            encoding="utf-8"
        )

    def test_closed_task_sections_left_in_plan_invalidate_decision(self) -> None:
        self.init(plan_reviewer((CONTINUE, PLAN_WITH_T1, False)))

        outcome = run_review(self.root)

        self.assertIsNone(outcome["review"]["decision"])
        error = outcome["review"]["error"]
        self.assertIn("### t1 本地设计", error)
        self.assertIn("### t1 boundary review", error)
        self.assertIn("plan-archive.md", error)
        self.assertNotIn("t2 本地设计", error)

    def test_moved_sections_keep_decision_and_open_task_headings(self) -> None:
        self.init(plan_reviewer((CONTINUE, PLAN_MOVED, False)))

        outcome = run_review(self.root)

        self.assertEqual(outcome["review"]["decision"], "continue")

    def assert_rereview_cannot_revive_old_decision(self, fail: bool) -> None:
        self.init(
            plan_reviewer(
                (CONTINUE, PLAN_MOVED, False),
                (None if fail else CONTINUE, PLAN_WITH_T1, fail),
            )
        )
        self.assertEqual(run_review(self.root)["review"]["decision"], "continue")

        outcome = run_review(self.root, objection="t2 input is wrong")

        self.assertIsNone(outcome["review"]["decision"])
        self.assertIn("### t1 boundary review", outcome["review"]["error"])
        with self.assertRaisesRegex(HarnessError, "awaiting reviewer decision"):
            initialize(
                self.root,
                task_id="t2",
                plan_doc="plan.md",
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )

    def test_failed_rereview_with_sections_written_back_drops_old_decision(self) -> None:
        self.assert_rereview_cannot_revive_old_decision(fail=True)

    def test_valid_rereview_with_sections_written_back_is_rejected(self) -> None:
        self.assert_rereview_cannot_revive_old_decision(fail=False)

    def test_prompt_names_sibling_archive_and_write_scope(self) -> None:
        self.init(plan_reviewer((CONTINUE, PLAN_MOVED, False)))
        run_review(self.root)

        prompt = self.prompt()

        self.assertIn("`plan-archive.md`", prompt)
        self.assertIn("文件相对链接不改", prompt)
        self.assertIn("只改 plan document、task 列表、`plan-archive.md`", prompt)

    def test_retry_prompt_carries_previous_error(self) -> None:
        self.init(
            plan_reviewer((CONTINUE, PLAN_WITH_T1, False), (CONTINUE, PLAN_MOVED, False))
        )
        run_review(self.root)

        run_review(self.root)

        self.assertIn("### t1 本地设计", self.prompt())


if __name__ == "__main__":
    unittest.main()
