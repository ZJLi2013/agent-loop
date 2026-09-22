from __future__ import annotations

import concurrent.futures
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from harness.core import (
    HarnessError,
    completion_gate,
    harness_dir,
    initialize,
    load_runtime,
    pause_request,
    request_pause,
    resume,
    run_command,
)


class HarnessPauseTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.plan = self.root / "plan.md"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write_plan(self, revision: int, review: str) -> None:
        self.plan.write_text(
            f"# Feature\n\nPlan Revision: {revision}\nPlan Review: {review}\n",
            encoding="utf-8",
        )

    def write_task(self, revision: int, runtime_dir: str = ".agent-loop") -> None:
        task_dir = self.root / runtime_dir
        task_dir.mkdir(exist_ok=True)
        (task_dir / "task.md").write_text(
            "| P | id | rev | task | check | status | failures |\n"
            "|---|---|---|---|---|---|---|\n"
            f"| P0 | t1 | r{revision} | test | command | 🔬 doing | 0 |\n",
            encoding="utf-8",
        )

    def init(self) -> None:
        initialize(
            self.root,
            task_id="t1",
            plan_doc="plan.md",
            verifier_argv=[sys.executable, "-c", "print('OK')"],
        )

    def test_proposed_plan_starts_paused(self) -> None:
        self.write_plan(1, "proposed")
        self.write_task(1)
        self.init()
        _, state = load_runtime(self.root)

        self.assertEqual(state["phase"], "paused")
        self.assertIsNotNone(pause_request(self.root))
        self.assertIsNone(completion_gate(self.root))
        with self.assertRaisesRegex(HarnessError, "runner is paused"):
            run_command(
                self.root,
                [sys.executable, "-c", "print('must not run')"],
                kind="exec",
            )

    def test_init_rejects_task_bound_to_another_revision(self) -> None:
        self.write_plan(2, "approved")
        self.write_task(1)
        with self.assertRaisesRegex(HarnessError, "binds r1, plan is r2"):
            self.init()

    def test_legacy_cursor_task_remains_readable(self) -> None:
        self.write_plan(1, "approved")
        self.write_task(1, ".cursor")
        self.init()
        _, state = load_runtime(self.root)

        self.assertEqual(state["phase"], "ready")

    def test_human_correction_requires_new_approved_revision(self) -> None:
        self.write_plan(1, "approved")
        self.write_task(1)
        self.init()
        request_pause(
            self.root,
            reason="human changed the goal",
            require_revision=True,
        )

        with self.assertRaisesRegex(HarnessError, "Revision to increase"):
            resume(self.root)

        self.write_plan(2, "proposed")
        with self.assertRaisesRegex(HarnessError, "must be approved"):
            resume(self.root)

        self.write_plan(2, "approved")
        with self.assertRaisesRegex(HarnessError, "binds r1"):
            resume(self.root)

        self.write_task(2)
        state = resume(self.root)
        self.assertEqual(state["phase"], "ready")
        self.assertEqual(state["plan_revision"], 2)
        self.assertEqual(state["plan_review"], "approved")
        self.assertIsNone(pause_request(self.root))

    def test_plan_drift_pauses_before_starting_another_command(self) -> None:
        self.write_plan(1, "approved")
        self.write_task(1)
        self.init()
        self.write_plan(2, "approved")

        with self.assertRaisesRegex(HarnessError, "revision changed"):
            run_command(
                self.root,
                [sys.executable, "-c", "print('must not run')"],
                kind="exec",
            )
        request = pause_request(self.root)
        self.assertIsNotNone(request)
        self.assertTrue(request["require_revision"])

    def test_pause_interrupts_a_running_process(self) -> None:
        self.write_plan(1, "approved")
        self.write_task(1)
        self.init()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                run_command,
                self.root,
                [sys.executable, "-c", "import time; time.sleep(30)"],
                kind="exec",
            )
            state_path = harness_dir(self.root) / "state.json"
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                state = json.loads(state_path.read_text())
                if state.get("phase") == "running":
                    break
                time.sleep(0.05)
            else:
                self.fail("runner never entered running state")

            request_pause(self.root, reason="human requested review")
            result = future.result(timeout=15)

        _, state = load_runtime(self.root)
        self.assertEqual(result["outcome"], "paused")
        self.assertTrue(result["paused"])
        self.assertEqual(state["phase"], "paused")
        self.assertLess(result["duration_seconds"], 15)


if __name__ == "__main__":
    unittest.main()

