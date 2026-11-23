from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness import failures, records
from harness.core import initialize, run_command, verify
from harness.records import close_task

RUNNER = Path(__file__).resolve().parents[1] / "harness" / "run.py"
TASKS = (
    "| id | task | check | status |\n|---|---|---|---|\n"
    "| t1 | 甲 [设计](plan.md#t1-design) | 过 → t2 | 🔬 doing |\n"
    "| t2 | 乙 | check | ⬜ todo |\n"
)
PLAN = "# Plan\n\nPlan Revision: 1\nPlan Review: approved\n\n### t1 design\n\n- rev：r1\n\nbody\n"
ROW = "| — | t1 | r1 | 甲 设计 | 过 → t2 | ✅ done | 2 |"


class FailureCountTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / ".agent-loop"
        self.runtime.mkdir()
        (self.runtime / "task.md").write_text(TASKS, encoding="utf-8")
        (self.runtime / "plan.md").write_text(PLAN, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def init(self) -> None:
        initialize(self.root, task_id="t1", verifier_argv=[sys.executable, "-S", "-c", "print('OK')"])

    def test_truncated_journal_keeps_the_count(self) -> None:
        self.init()
        failures.add(self.root, "t1", "first")
        run_command(self.root, [sys.executable, "-S", "-c", "raise SystemExit(1)"], kind="exec")
        failures.add(self.root, "t1", "second")

        (self.root / ".harness" / "runs.jsonl").write_text("", encoding="utf-8")

        self.assertEqual(failures.count(self.root, "t1"), 2)

    def test_plain_exec_success_does_not_reset(self) -> None:
        self.init()
        failures.add(self.root, "t1", "first")
        run_command(self.root, [sys.executable, "-S", "-c", "print('ok')"], kind="exec")
        failures.add(self.root, "t1", "second")
        self.assertEqual(failures.count(self.root, "t1"), 2)

        verify(self.root)

        self.assertEqual(failures.count(self.root, "t1"), 0)

    def test_concurrent_fail_counts_both(self) -> None:
        argv = [sys.executable, str(RUNNER), "--root", str(self.root), "fail", "--task", "t1", "--note", "x"]
        processes = [subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE) for _ in range(2)]
        errors = [process.communicate()[1] for process in processes]

        self.assertEqual([process.returncode for process in processes], [0, 0], errors)
        self.assertEqual(failures.count(self.root, "t1"), 2)

    def test_fail_refuses_an_unknown_task(self) -> None:
        argv = [sys.executable, str(RUNNER), "--root", str(self.root), "fail", "--task", "t9", "--note", "x"]
        result = subprocess.run(argv, capture_output=True, text=True)

        self.assertEqual(result.returncode, 2)
        self.assertIn("not in the task list", result.stderr)

    def test_interrupted_close_archives_once_and_takes_once(self) -> None:
        for step, target in (("remove", (records, "_remove_closed")), ("take", (records.failures, "take"))):
            with self.subTest(step):
                self.tearDown()
                self.setUp()
                failures.add(self.root, "t1", "first")
                failures.add(self.root, "t1", "second")

                with mock.patch.object(*target, side_effect=OSError("interrupted")):
                    with self.assertRaises(OSError):
                        close_task(self.root, ".agent-loop/plan.md", "t1")
                close_task(self.root, ".agent-loop/plan.md", "t1")

                archive = (self.runtime / "archive" / "tasks.md").read_text(encoding="utf-8")
                self.assertEqual(archive.count("| t1 |"), 1, archive)
                self.assertIn(ROW, archive)
                self.assertEqual(failures.count(self.root, "t1"), 0)
                self.assertNotIn("| t1 |", (self.runtime / "task.md").read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
