from __future__ import annotations

import concurrent.futures
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path

from harness.attention import record_goal_review
from harness.core import (
    HarnessError,
    completion_gate,
    disable,
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
            f"# Feature\n\nPlan Revision: {revision}\nPlan Review: {review}\n\n## t1 design\n",
            encoding="utf-8",
        )

    def write_task(self, revision: int, runtime_dir: str = ".agent-loop") -> None:
        task_dir = self.root / runtime_dir
        task_dir.mkdir(exist_ok=True)
        (task_dir / "task.md").write_text(
            "| P | id | rev | task | check | status | failures |\n"
            "|---|---|---|---|---|---|---|\n"
            f"| P0 | t1 | r{revision} | test | [design](../plan.md#t1-design) | 🔬 doing | 0 |\n",
            encoding="utf-8",
        )

    def init(self) -> None:
        initialize(
            self.root,
            task_id="t1",
            plan_doc="plan.md",
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
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
                [sys.executable, "-S", "-c", "print('must not run')"],
                kind="exec",
            )

    def test_init_rejects_task_bound_to_another_revision(self) -> None:
        self.write_plan(2, "approved")
        self.write_task(1)
        with self.assertRaisesRegex(HarnessError, "binds r1, plan is r2"):
            self.init()

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
        self.assertEqual(
            {key: state["revision_source"][key] for key in ("from", "to", "reason")},
            {"from": 1, "to": 2, "reason": "human changed the goal"},
        )
        self.assertIsNone(pause_request(self.root))

    def test_a_revision_bump_without_a_source_is_refused(self) -> None:
        self.write_plan(1, "approved")
        self.write_task(1)
        self.init()
        self.write_plan(2, "approved")
        self.write_task(2)

        with self.assertRaisesRegex(HarnessError, "runner is paused"):
            run_command(self.root, [sys.executable, "-S", "-c", "print('x')"], kind="exec")
        self.assertFalse(pause_request(self.root)["require_revision"])
        with self.assertRaisesRegex(HarnessError, "without a recorded source"):
            resume(self.root)
        self.assertIsNotNone(pause_request(self.root))

        disable(self.root)
        with self.assertRaisesRegex(HarnessError, "without a recorded source"):
            self.init()
        request_pause(self.root, reason="human changed the goal", require_revision=True)
        self.init()
        self.assertEqual(load_runtime(self.root)[1]["revision_source"]["to"], 2)

    def test_a_goal_review_replan_is_a_source(self) -> None:
        self.write_plan(1, "approved")
        self.write_task(1)
        initialize(
            self.root, task_id="t1", plan_doc="plan.md",
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"], goal_review_after_actions=1,
        )
        run_command(self.root, [sys.executable, "-S", "-c", "print('x')"], kind="exec")
        record_goal_review(self.root, decision="replan", evidence="the next action no longer serves the Goal")
        self.write_plan(2, "approved")
        self.write_task(2)

        state = resume(self.root)

        self.assertEqual(state["revision_source"]["reason"], "Goal Review chose replan")

    def test_a_successor_without_a_bump_keeps_the_source(self) -> None:
        self.write_plan(1, "approved")
        self.write_task(1)
        self.init()
        request_pause(self.root, reason="human changed the goal", require_revision=True)
        self.write_plan(2, "approved")
        self.write_task(2)
        resume(self.root)
        disable(self.root)

        self.init()

        self.assertEqual(load_runtime(self.root)[1]["revision_source"]["reason"], "human changed the goal")

    def test_pause_and_resume_refuse_a_closed_task(self) -> None:
        self.write_plan(1, "approved")
        self.write_task(1)
        self.init()
        request_pause(self.root, reason="human requested review")
        task = self.root / ".agent-loop" / "task.md"
        task.write_text(
            task.read_text(encoding="utf-8").replace("🔬 doing", "✅ done"),
            encoding="utf-8",
        )

        with self.assertRaisesRegex(HarnessError, "init its successor"):
            resume(self.root)
        with self.assertRaisesRegex(HarnessError, "init its successor"):
            request_pause(self.root, reason="another review")

        request_pause(self.root, reason="human changed the goal", require_revision=True)
        with self.assertRaisesRegex(HarnessError, "Revision to increase"):
            resume(self.root)

    def test_pause_interrupts_a_running_process(self) -> None:
        self.write_plan(1, "approved")
        self.write_task(1)
        self.init()
        with concurrent.futures.ThreadPoolExecutor() as pool:
            future = pool.submit(
                run_command,
                self.root,
                [sys.executable, "-S", "-c", "import time; time.sleep(30)"],
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
