from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from harness import records
from harness.core import (
    HarnessError,
    clean_scratch,
    completion_gate,
    initialize,
    load_runtime,
    run_command,
    verify,
)
from harness.plan import pause_request, request_pause
from harness.plan_review import record_task_review, respond_task, run_plan_review, task_record
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
        handoff = completion_gate(self.root, None, "new_session") or ""
        self.assertIn("no reviewer is configured", handoff)
        self.assertIn("disable", handoff)
        with self.assertRaisesRegex(HarnessError, "no reviewer configured"):
            run_review(self.root)

    def test_verified_task_requires_review_then_hands_off_next_task(self) -> None:
        self.init(reviewer_writing(
            {"decision": "continue", "next_task": "t2", "why": "next hypothesis"}
        ))
        self.assertIn("review", completion_gate(self.root) or "")
        scratch = self.root / ".harness" / "tasks" / "t1"
        (scratch / "kit.py").write_text("print(1)\n", encoding="utf-8")

        outcome = run_review(self.root)
        prompt = (self.root / ".harness" / "review" / "prompt.md").read_text(
            encoding="utf-8"
        )

        self.assertEqual(outcome["review"]["decision"], "continue")
        self.assertFalse(scratch.exists())
        self.assertIsNone(outcome["review"]["cleanup_error"])
        self.assertIn("t1", prompt)
        self.assertIn(".agent-loop/task.md", prompt)
        followup = completion_gate(self.root) or ""
        self.assertIn("t2", followup)
        self.assertIn("--objection", followup)
        self.assertNotIn("stale", followup)

    def test_closing_review_archives_old_handoffs_and_reports_failures(self) -> None:
        real_write = records._atomic_write
        for blocked in (False, True):
            with self.subTest(blocked=blocked):
                if blocked:
                    self.tearDown()
                    self.setUp()
                progress = self.root / ".agent-loop" / "progress.md"
                progress.write_text("## new\nnow\n\n## old\nthen\n", encoding="utf-8")
                self.init(reviewer_writing({"decision": "continue", "next_task": "t2", "why": "next"}))

                def write(path: Path, text: str) -> None:
                    if blocked and path.name == "progress.md":
                        raise PermissionError(13, "locked")
                    real_write(path, text)

                with mock.patch("harness.records._atomic_write", side_effect=write):
                    review = run_review(self.root)["review"]

                self.assertEqual(review["decision"], "continue")
                self.assertEqual(review["progress_archived"], 0 if blocked else 1)
                self.assertEqual("cannot archive progress.md" in (review["cleanup_error"] or ""), blocked)
                self.assertEqual("## old" in progress.read_text(encoding="utf-8"), blocked)
                self.assertNotIn("| t1 |", (self.root / ".agent-loop" / "task.md").read_text(encoding="utf-8"))
                self.assertFalse((self.root / ".harness" / "tasks" / "t1").exists())

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

    def test_successor_must_be_an_open_task(self) -> None:
        self.init(reviewer_writing({"decision": "continue", "next_task": "t1", "why": "again"}))

        review = run_review(self.root)["review"]

        self.assertIsNone(review["decision"])
        self.assertIn("must be an open task", review["error"])

    def test_successor_sharing_another_tasks_record_is_refused(self) -> None:
        self.init(reviewer_writing(
            {"decision": "continue", "next_task": "t2", "why": "next hypothesis"}
        ))
        record = self.root / ".harness" / "plan-review" / "tasks" / "t2.json"
        record.parent.mkdir(parents=True, exist_ok=True)
        record.write_text(
            json.dumps({"task_id": "T2", "reviews": [], "approvals": [], "again": []}),
            encoding="utf-8",
        )

        review = run_review(self.root)["review"]

        self.assertIsNone(review["decision"])
        self.assertIn("rename the task", review["error"])

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

REVISE = {"decision": "revise", "why": "t1 fact only in .agent-loop", "findings": [
    {"level": "must", "claim": "usage.md lacks the default", "consequence": "lost on clone", "evidence": "plan.md:3"}
]}


def reviewer_sequence(*decisions: dict[str, object]) -> list[str]:
    code = "\n".join(
        [
            "import json",
            "from pathlib import Path",
            "counter = Path('.harness/review/calls.txt')",
            "n = int(counter.read_text()) if counter.exists() else 0",
            "counter.write_text(str(n + 1))",
            f"Path({DECISION!r}).write_text(json.dumps(json.loads({json.dumps(decisions)!r})[n]))",
        ]
    )
    return [sys.executable, "-S", "-c", code]


class VerifierLockReviewTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".agent-loop").mkdir()
        (self.root / ".agent-loop" / "task.md").write_text(
            REWRITTEN_TASKS.replace("✅ done", "🔬 doing"), encoding="utf-8"
        )
        (self.root / ".agent-loop" / "reviewer.json").write_text(json.dumps({
            "argv": reviewer_writing({"decision": "continue", "next_task": "t2", "why": "next"}),
            "timeout_seconds": 30,
        }))
        self.verifier = self.root / ".harness" / "tasks" / "t1" / "verify.py"
        self.verifier.parent.mkdir(parents=True)
        self.verifier.write_text("print('OK')\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_review_refuses_a_changed_verifier(self) -> None:
        initialize(
            self.root,
            task_id="t1",
            verifier_argv=[sys.executable, "-S", ".harness/tasks/t1/verify.py"],
        )
        run_command(self.root, [sys.executable, "-S", ".harness/tasks/t1/verify.py"], kind="verify")
        self.verifier.write_text("print('OK')  # edited after verify\n")

        with self.assertRaisesRegex(HarnessError, "verify.py changed after init"):
            run_review(self.root)
        self.assertIsNone(load_runtime(self.root)[1].get("review"))

    def test_gate_rechecks_the_verifier_after_an_invalid_review(self) -> None:
        (self.root / ".agent-loop" / "reviewer.json").write_text(json.dumps({
            "argv": reviewer_writing({"decision": "continue", "why": "no task"}),
            "timeout_seconds": 30,
        }))
        initialize(
            self.root,
            task_id="t1",
            verifier_argv=[sys.executable, "-S", ".harness/tasks/t1/verify.py"],
        )
        run_command(self.root, [sys.executable, "-S", ".harness/tasks/t1/verify.py"], kind="verify")
        self.assertIsNone(run_review(self.root)["review"]["decision"])
        self.verifier.write_text("print('OK')  # edited after an invalid review\n")

        message = completion_gate(self.root) or ""

        self.assertIn("stale", message)
        self.assertIn("verify.py", message)
        self.assertEqual(load_runtime(self.root)[1]["phase"], "failed")


class ReviseTest(unittest.TestCase):
    setUp = TaskBoundaryReviewTest.setUp
    tearDown = TaskBoundaryReviewTest.tearDown
    init = TaskBoundaryReviewTest.init

    def test_revise_keeps_the_task_open_until_it_is_verified_again(self) -> None:
        self.init(reviewer_sequence(REVISE, {**CONTINUE}), run_verifier=False)
        scratch = self.root / ".harness" / "tasks" / "t1"
        (scratch / "kit.py").write_text("print(1)\n", encoding="utf-8")

        review = verify(self.root)["automatic_review"]
        tasks = self.root / ".agent-loop" / "task.md"

        self.assertEqual((review["decision"], review["error"]), ("revise", None))
        self.assertIn("| t1 | — | first | check | 🔬 doing |", tasks.read_text(encoding="utf-8"))
        self.assertTrue((scratch / "kit.py").exists())
        followup = completion_gate(self.root) or ""
        self.assertIn("sent t1 back", followup)
        self.assertIn("verify", followup)
        with self.assertRaisesRegex(HarnessError, "sent t1 back"):
            clean_scratch(self.root)
        with self.assertRaisesRegex(HarnessError, "sent t1 back"):
            initialize(self.root, task_id="t2", verifier_argv=[sys.executable, "-S", "-c", "pass"])
        self.assertTrue((scratch / "kit.py").exists())

        run_command(self.root, [sys.executable, "-S", "-c", "print('close')"], kind="exec")
        second = verify(self.root)["automatic_review"]

        self.assertEqual((second["decision"], second["attempts"]), ("continue", 1))
        self.assertNotIn("| t1 |", tasks.read_text(encoding="utf-8"))
        self.assertFalse(scratch.exists())

    def test_other_decisions_still_block_execution(self) -> None:
        self.init(reviewer_sequence({"decision": "ask_human", "why": "pick"}), run_verifier=False)
        verify(self.root)
        with self.assertRaisesRegex(HarnessError, "execution remains blocked"):
            run_command(self.root, [sys.executable, "-S", "-c", "pass"], kind="exec")

    def test_revise_is_allowed_once_per_task(self) -> None:
        with self.subTest("a second verify cannot be sent back again"):
            self.init(reviewer_sequence(REVISE, REVISE), run_verifier=False)
            verify(self.root)
            review = verify(self.root)["automatic_review"]
            self.assertIsNone(review["decision"])
            self.assertIn("once per task", review["error"])
        self.tearDown()
        self.setUp()
        with self.subTest("an objection on the same verify may keep revise"):
            self.init(reviewer_sequence(REVISE, REVISE), run_verifier=False)
            verify(self.root)
            review = run_review(self.root, objection="the default is in usage.md")["review"]
            self.assertEqual((review["decision"], review["error"]), ("revise", None))
        self.tearDown()
        self.setUp()
        with self.subTest("a new task may revise once"):
            self.init(reviewer_sequence(REVISE, CONTINUE, REVISE), run_verifier=False)
            verify(self.root)
            verify(self.root)
            tasks = self.root / ".agent-loop" / "task.md"
            tasks.write_text(tasks.read_text(encoding="utf-8").replace("📝 proposed", "🔬 doing"), encoding="utf-8")
            initialize(self.root, task_id="t2", verifier_argv=[sys.executable, "-S", "-c", "print('OK')"])
            review = verify(self.root)["automatic_review"]
            self.assertEqual((review["decision"], review["error"]), ("revise", None))


CONTINUE = {"decision": "continue", "next_task": "t2", "why": "next hypothesis"}
PLAN_HEAD = "# Plan\n\nPlan Revision: 1\nPlan Review: unreviewed\n\n## 脉络\nt2\n"
PLAN_WITH_T1 = (
    PLAN_HEAD
    + '\n<a id="t1-design"></a>\n### t1 本地设计\ninput\n### t1 boundary review\nok\n'
    + "### t2 本地设计\nnext\n"
)
PLAN_MOVED = PLAN_HEAD + "\nt1 已归档：[plan-archive.md](plan-archive.md)\n### t2 本地设计\nnext\n"
PLAN_TASKS = (
    REWRITTEN_TASKS.replace("| — |", "| r1 |")
    .replace("| first | check |", "| first | [设计](../plan.md#t1-design) |")
    .replace("| next | check |", "| next | [设计](../plan.md#t2-本地设计) |")
)


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
    "| P0 | t2 | r{revision} | next | [设计](../plan.md#t2-本地设计) | 🔬 doing | 0 |\n"
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

    def test_correction_pause_admits_a_reviewed_new_task(self) -> None:
        cases = (
            ("continue", {}, None),
            ("stop", {"decision": "stop"}, None),
            ("same file", {"plan_doc": "./plan.md"}, None),
            ("no request", {"pause": None}, "unattended after"),
            ("ordinary request", {"pause": False}, "unattended after"),
            ("unchanged revision", {"revision": 1}, "unattended after"),
            ("older revision", {"revision": 0}, "unattended after"),
            ("different plan", {"plan_doc": "other.md"}, "unattended after"),
            ("not doing", {"status": "⬜ todo"}, "must be approved as 🔬 doing"),
            ("old task binding", {"task_revision": 1}, "binds r1, plan is r3"),
            ("unanswered must", {"respond": False}, "must items"),
            ("human decision", {"human": True}, "human to decide"),
        )
        for name, options, error in cases:
            with self.subTest(name):
                self.tearDown()
                self.setUp()
                decision = options.get("decision", "continue")
                self.review_as(decision, "t2" if decision == "continue" else None)
                tasks = self.root / ".agent-loop" / "task.md"
                self.assertNotIn("| t1 |", tasks.read_text(encoding="utf-8"))
                with self.assertRaisesRegex(HarnessError, "init its successor"):
                    request_pause(self.root, reason="ordinary pause after CLOSE")
                self.assertIsNone(pause_request(self.root))

                pause_path = self.root / ".harness" / "pause.json"
                if options.get("pause", True) is not None:
                    request_pause(self.root, reason="human: t3 before t2", require_revision=True)
                    if options.get("pause") is False:
                        # A saved ordinary request, such as one left by an older version.
                        request = pause_request(self.root)
                        request["require_revision"] = False
                        pause_path.write_text(json.dumps(request), encoding="utf-8")

                revision = options.get("revision", 3)
                plan_doc = options.get("plan_doc", "plan.md")
                plan = PLAN_MOVED.replace("Plan Revision: 1", f"Plan Revision: {revision}")
                (self.root / plan_doc).write_text(plan + "\n## t3 design\ncorrected scope\n", encoding="utf-8")
                row = SUCCESSOR_TASKS.format(revision=options.get("task_revision", revision))
                row = row.replace("t2", "t3").replace("t3-本地设计", "t3-design")
                row = row.replace("../plan.md", f"../{plan_doc}")
                row = row.replace("🔬 doing", options.get("status", "🔬 doing"))
                tasks.write_text(
                    row + "| P1 | t2 | r1 | waits | [design](../plan.md#t2-本地设计) | ⬜ todo | 0 |\n",
                    encoding="utf-8",
                )
                must = {
                    "level": "must", "claim": "check the corrected scope",
                    "consequence": "the verifier checks the old priority",
                    "evidence": "plan.md", "change": "use a new verifier",
                    "human": options.get("human", False),
                }
                report = json.dumps({"summary": "check scope", "tasks": {
                    "t2": {"findings": []}, "t3": {"findings": [must]},
                }})
                reviewer = [sys.executable, "-S", "-c", (
                    "from pathlib import Path; "
                    f"Path('.harness/plan-review/report.json').write_text({report!r})"
                )]
                run_plan_review(
                    self.root, plan_doc=plan_doc,
                    reviewer_config={"argv": reviewer, "timeout_seconds": 30},
                )
                if options.get("respond", True):
                    respond_task(self.root, "t3", items=["1=applied"])
                (self.root / ".agent-loop" / "reviewer.json").write_text(json.dumps({
                    "argv": reviewer_decision_only({"decision": "stop", "why": "corrected task verified"}),
                    "timeout_seconds": 30,
                }), encoding="utf-8")
                before = load_runtime(self.root)
                request_before = pause_path.read_bytes() if pause_path.exists() else None
                verifier = [sys.executable, "-S", "-c", "print('corrected task verified')"]
                kwargs = dict(
                    task_id="t3", plan_doc=plan_doc, verifier_argv=verifier,
                    max_attempts=5, max_wall_seconds=90,
                )
                if error:
                    with self.assertRaises(HarnessError) as rejected:
                        initialize(self.root, **kwargs)
                    if error == "unattended after":
                        self.assertIn(error, str(rejected.exception))
                    self.assertEqual(load_runtime(self.root), before)
                    self.assertEqual(
                        pause_path.read_bytes() if pause_path.exists() else None, request_before
                    )
                else:
                    try:
                        config, state = initialize(self.root, **kwargs)
                    except HarnessError as exc:
                        self.fail(f"reviewed human correction must admit t3: {exc}")
                    self.assertEqual(state["task_id"], "t3")
                    self.assertEqual(state["phase"], "ready")
                    self.assertEqual(state["plan_revision"], 3)
                    self.assertEqual(state["plan_review"], "unreviewed")
                    self.assertEqual(state["verify_attempts"], 0)
                    self.assertEqual(config["verifier"]["argv"], verifier)
                    self.assertEqual(config["budget"], {"max_attempts": 5, "max_wall_seconds": 90.0})
                    self.assertFalse(pause_path.exists())
                    result = verify(self.root)
                    self.assertTrue(result["verification_passed"])
                    self.assertEqual(result["automatic_review"]["decision"], "stop")
                    stdout = self.root / ".harness" / "artifacts" / result["run_id"] / "stdout.log"
                    self.assertEqual(stdout.read_text().strip(), "corrected task verified")

    def test_successor_is_plan_reviewed_before_init(self) -> None:
        cases = (
            ("reviewer-named successor", "t2", False, "unreviewed", True),
            ("record left by the old shortcut", "t2", True, "unreviewed", True),
            ("successor under an approved plan", "t2", False, "approved", True),
            ("unnamed task under an approved plan", None, False, "approved", False),
        )
        for name, next_task, legacy, review, starts in cases:
            with self.subTest(name):
                self.tearDown()
                self.setUp()
                tasks = self.root / ".agent-loop" / "task.md"
                tasks.write_text(
                    "\n".join(tasks.read_text(encoding="utf-8").splitlines()[:3]) + "\n",
                    encoding="utf-8",
                )
                self.review_as("continue" if next_task else "stop", next_task)
                if legacy:
                    record_task_review(
                        self.root, "t2", findings=[], dropped=0, summary="", source="task_review",
                        run_id=None, plan_doc="plan.md",
                    )
                self.human_decides(1, review)
                if starts:
                    self.init_successor()
                else:
                    with self.assertRaisesRegex(HarnessError, "set Plan Review to proposed"):
                        self.init_successor()
                sources = [item["source"] for item in task_record(self.root, "t2")["reviews"]]
                self.assertEqual("plan_review" in sources, starts)

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
    "| P0 | {task} | r1 | next | [设计](../next/plan.md#t2-design) | 🔬 doing | 0 |\n"
)
NEXT_PLAN = "# Next\n\nPlan Revision: 1\nPlan Review: unreviewed\n\n## t2 design\n"


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
            (self.root / name / "plan.md").write_text(NEXT_PLAN, encoding="utf-8")
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

    def test_hands_off_only_to_the_next_aligned_goal(self) -> None:
        cases = (
            ("next aligned goal", "stop", [DONE_A, NEXT_B, TODO_C], {}, True),
            ("unapproved mainline", "stop", [DONE_A, NEXT_B], {"review": "proposed"}, False),
            ("skipped goal", "stop", [DONE_A, TODO_C, NEXT_B], {}, False),
            ("plan outside next goal", "stop", [DONE_A, NEXT_B], {"plan": "side/plan.md"}, False),
            ("no mainline", "stop", None, {}, False),
            ("continue within goal", "continue", [DONE_A, NEXT_B], {"task": "t3", "plan": "plan.md"}, False),
            ("side goal closed", "stop", [DONE_SIDE, NEXT_B], {}, False),
        )
        for name, decision, rows, options, starts in cases:
            with self.subTest(name):
                self.tearDown()
                self.setUp()
                self.review_as(decision, "t2" if decision == "continue" else None)
                if starts:
                    self.assertEqual(self.start(rows, **options)["task_id"], "t2")
                else:
                    with self.assertRaisesRegex(HarnessError, "unattended after"):
                        self.start(rows, **options)

    def test_handoff_still_needs_answered_plan_review(self) -> None:
        self.review_as("stop")
        must = {
            "level": "must", "claim": "wrong input", "consequence": "wasted run",
            "evidence": "plan:1", "change": "fix input", "human": False,
        }
        (self.root / "next").mkdir()
        (self.root / "next" / "plan.md").write_text(NEXT_PLAN, encoding="utf-8")
        record_task_review(
            self.root, "t2", findings=[must], dropped=0, summary="", source="plan_review", run_id=None,
            plan_doc="next/plan.md",
        )
        with self.assertRaisesRegex(HarnessError, "must items"):
            self.start([DONE_A, NEXT_B])

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
    "## 脉络\n| t1 | 甲 | [t1 设计](#t1-design) | 做 t2 |\n\n"
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
        self.assertIn("## 脉络\n| t1 | 甲 | [t1 设计](plan-archive.md#t1-design) | 做 t2 |", plan)
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
