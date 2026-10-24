from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness import run
from harness.core import HarnessError, clean_scratch, initialize, load_runtime, verify


class TaskScratchTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.scratch = self.root / ".harness" / "tasks" / "t1"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def init(self, task_id: str = "t1") -> None:
        initialize(
            self.root,
            task_id=task_id,
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
        )

    def test_init_creates_scratch_and_status_reports_strays(self) -> None:
        self.init()
        self.assertTrue(self.scratch.is_dir())
        (self.root / ".harness" / "t1_kit").mkdir()
        (self.root / ".harness" / "tasks" / "t0").mkdir()
        (self.root / ".harness" / ".state.json.1.tmp").write_text("{}", encoding="utf-8")

        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(run.main(["--root", str(self.root), "status"]), 0)
        status = json.loads(out.getvalue())

        self.assertEqual(status["scratch"], ".harness/tasks/t1")
        self.assertEqual(status["strays"], ["t1_kit", "tasks/t0"])

    def test_clean_task_waits_for_the_verifier_then_removes_scratch(self) -> None:
        self.init()
        (self.scratch / "kit.py").write_text("print(1)\n", encoding="utf-8")
        with self.assertRaisesRegex(HarnessError, "after the locked verifier passes"):
            clean_scratch(self.root)

        verify(self.root)

        self.assertIsNone(clean_scratch(self.root)["error"])
        self.assertFalse(self.scratch.exists())
        self.assertIsNone(clean_scratch(self.root)["error"])

    def test_removal_failure_is_reported_without_changing_the_task(self) -> None:
        self.init()
        verify(self.root)

        with mock.patch("harness.scratch.shutil.rmtree", side_effect=PermissionError(13, "locked")):
            outcome = clean_scratch(self.root)

        self.assertIn("cannot remove .harness/tasks/t1", outcome["error"])
        self.assertEqual(load_runtime(self.root)[1]["phase"], "verified")

    def test_task_id_must_be_one_path_segment(self) -> None:
        with self.assertRaisesRegex(HarnessError, "single path segment"):
            self.init("../t1")
        self.assertFalse((self.root / ".harness" / "state.json").exists())


if __name__ == "__main__":
    unittest.main()
