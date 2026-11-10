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
from harness.plan_review import run_plan_review
from harness.records import archive_closed_tasks


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
        self.assertIsNone(pause_request(self.root))

    def test_pause_rejects_closed_or_missing_task(self) -> None:
        self.write_plan(1, "proposed")
        self.write_task(1)
        report = json.dumps({"summary": "ready", "tasks": {"t1": {"findings": []}}})
        reviewer = {
            "argv": [
                sys.executable, "-S", "-c",
                "from pathlib import Path; "
                f"Path('.harness/plan-review/report.json').write_text({report!r})",
            ],
        }
        (self.root / ".agent-loop" / "reviewer.json").write_text(
            json.dumps(reviewer), encoding="utf-8"
        )
        run_plan_review(self.root, plan_doc="plan.md")
        self.write_plan(1, "approved")
        self.init()
        run_command(
            self.root, [sys.executable, "-S", "-c", "print('OK')"], kind="verify"
        )
        state_path = harness_dir(self.root) / "state.json"
        before = state_path.read_bytes()
        self.assertEqual(load_runtime(self.root)[1]["phase"], "verified")
        task = self.root / ".agent-loop" / "task.md"
        active = task.read_text(encoding="utf-8")

        for status in ("✅ done", "❌ dropped", "archived", "missing", "no task file"):
            with self.subTest(status=status):
                if status == "no task file":
                    task.unlink()
                elif status == "missing":
                    task.write_text(active.replace("t1", "t2"), encoding="utf-8")
                else:
                    closed = "✅ done" if status == "archived" else status
                    task.write_text(active.replace("🔬 doing", closed), encoding="utf-8")
                    if status == "archived":
                        self.assertEqual(archive_closed_tasks(self.root), ["t1"])
                with self.assertRaisesRegex(HarnessError, "task t1.*closed or missing"):
                    request_pause(self.root, reason="wait for PR merge")
                self.assertIsNone(pause_request(self.root))
                self.assertEqual(state_path.read_bytes(), before)

        task.write_text(active, encoding="utf-8")
        request_pause(self.root, reason="review open task")
        self.assertEqual(resume(self.root)["phase"], "ready")
        self.assertIsNone(pause_request(self.root))

    def test_pause_resume_without_plan_or_task_list(self) -> None:
        initialize(
            self.root,
            task_id="t1",
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
        )
        request_pause(self.root, reason="human requested review")
        self.assertIsNotNone(pause_request(self.root))
        self.assertEqual(resume(self.root)["phase"], "ready")
        self.assertIsNone(pause_request(self.root))

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
