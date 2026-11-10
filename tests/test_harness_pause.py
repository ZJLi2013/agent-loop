from __future__ import annotations

import concurrent.futures
import contextlib
import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

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

from harness.plan_review import record_task_review
from harness.storage import atomic_write_json, state_lock


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


class HarnessPauseEligibilityTest(unittest.TestCase):
    def write_plan(self, root: Path, revision: int = 1, review: str = "approved") -> None:
        (root / "plan.md").write_text(
            f"# Plan\n\nPlan Revision: {revision}\nPlan Review: {review}\n\n## t1 design\n",
            encoding="utf-8",
        )

    def write_task(
        self, root: Path, status: str = "🔬 doing", revision: int = 1,
        task_id: str = "t1",
    ) -> None:
        directory = root / ".agent-loop"
        directory.mkdir(exist_ok=True)
        (directory / "task.md").write_text(
            "| P | id | rev | task | check | status | failures |\n"
            "|---|---|---|---|---|---|---|\n"
            f"| P0 | {task_id} | r{revision} | test | [design](../plan.md#t1-design) | {status} | 0 |\n",
            encoding="utf-8",
        )

    def record_review(self, root: Path) -> None:
        record_task_review(
            root, "t1", findings=[], dropped=0, summary="ready",
            source="plan_review", run_id=None, plan_doc="plan.md",
        )

    @contextlib.contextmanager
    def project(self, *, bound: bool = True, reviewer: bool = False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            if bound:
                self.write_plan(root)
                self.write_task(root)
            if reviewer:
                runtime = root / ".agent-loop"
                runtime.mkdir(exist_ok=True)
                atomic_write_json(runtime / "reviewer.json", {
                    "argv": [sys.executable, "-S", "-c", "raise SystemExit('unexpected review')"],
                })
                if bound:
                    self.record_review(root)
            _, state = initialize(
                root, task_id="t1", plan_doc="plan.md" if bound else None,
                verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
            )
            state["phase"] = "verified"
            atomic_write_json(harness_dir(root) / "state.json", state)
            yield root

    def make_unavailable(self, root: Path, availability: str) -> None:
        if availability in {"done", "dropped"}:
            self.write_task(root, "✅ done" if availability == "done" else "❌ dropped")
            return
        task = root / ".agent-loop" / "task.md"
        if availability == "archived":
            self.write_task(root, "✅ done")
            archive = task.parent / "archive"
            archive.mkdir()
            task.replace(archive / "tasks.md")
        if availability == "no_task_file":
            task.unlink()
        else:
            self.write_task(root, task_id="t2")

    def legacy_pause(self, root: Path) -> None:
        # A request accepted by an older version after this task had already closed.
        atomic_write_json(harness_dir(root) / "pause.json", {
            "reason": "wait for PR merge", "kind": "human", "require_revision": False,
            "requested_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
        })

    def assert_resume_refused(self, root: Path) -> str:
        state_path = harness_dir(root) / "state.json"
        pause_path = harness_dir(root) / "pause.json"
        state_before, pause_before = state_path.read_bytes(), pause_path.read_bytes()
        with self.assertRaises(HarnessError) as caught:
            resume(root)
        self.assertEqual(state_path.read_bytes(), state_before)
        self.assertEqual(pause_path.read_bytes(), pause_before)
        return str(caught.exception)

    def test_resume_rejects_closed_task_still_in_table(self) -> None:
        for reviewer in (False, True):
            for status in ("done", "dropped"):
                with self.subTest(reviewer=reviewer, status=status), self.project(reviewer=reviewer) as root:
                    self.make_unavailable(root, status)
                    self.legacy_pause(root)
                    reason = self.assert_resume_refused(root)
                    with self.assertRaises(HarnessError) as caught:
                        request_pause(root, reason="wait")
                    self.assertEqual(reason, str(caught.exception))
                    self.assertIn("task t1", reason)
                    self.assertIn("init", reason)
                    self.assertIn("successor", reason)

    def test_bound_pause_and_resume_reject_unavailable_task(self) -> None:
        for reviewer in (False, True):
            for availability in ("done", "dropped", "archived", "missing", "no_task_file"):
                for origin in ("closed_after_pause", "legacy"):
                    with self.subTest(reviewer=reviewer, availability=availability, origin=origin):
                        with self.project(reviewer=reviewer) as root:
                            if origin == "closed_after_pause":
                                request_pause(root, reason="wait")
                                saved_pause = pause_request(root)
                            self.make_unavailable(root, availability)
                            (harness_dir(root) / "pause.json").unlink(missing_ok=True)
                            state_path = harness_dir(root) / "state.json"
                            before = state_path.read_bytes()
                            with mock.patch("harness.plan_review.run_plan_review") as run_review:
                                with self.assertRaises(HarnessError) as caught:
                                    request_pause(root, reason="wait")
                                self.assertIsNone(pause_request(root))
                                self.assertEqual(state_path.read_bytes(), before)
                                if origin == "closed_after_pause":
                                    atomic_write_json(harness_dir(root) / "pause.json", saved_pause)
                                else:
                                    self.legacy_pause(root)
                                reason = self.assert_resume_refused(root)
                                self.assertEqual(reason, str(caught.exception))
                                self.assertIn("task t1", reason)
                                self.assertIn("init", reason)
                                self.assertIn("successor", reason)
                                run_review.assert_not_called()

    def test_open_bound_task_can_pause_and_resume(self) -> None:
        for reviewer in (False, True):
            with self.subTest(reviewer=reviewer), self.project(reviewer=reviewer) as root:
                request_pause(root, reason="wait")
                self.assertIsNotNone(pause_request(root))
                state = resume(root)
                self.assertEqual(state["phase"], "ready")
                self.assertEqual(state["plan_revision"], 1)
                self.assertIsNone(pause_request(root))

    def test_unbound_task_missing_from_table_can_pause_and_resume(self) -> None:
        for reviewer in (False, True):
            with self.subTest(reviewer=reviewer), self.project(bound=False, reviewer=reviewer) as root:
                self.write_task(root, task_id="t2")
                try:
                    request_pause(root, reason="wait")
                    self.assertIsNotNone(pause_request(root))
                    state = resume(root)
                except HarnessError as exc:
                    self.fail(f"unbound task must support pause and resume: {exc}")
                self.assertEqual(state["phase"], "ready")
                self.assertIsNone(state["plan_revision"])
                self.assertIsNone(pause_request(root))

    def test_unbound_task_without_table_can_pause_and_resume(self) -> None:
        for reviewer in (False, True):
            with self.subTest(reviewer=reviewer), self.project(bound=False, reviewer=reviewer) as root:
                self.assertFalse((root / ".agent-loop" / "task.md").exists())
                request_pause(root, reason="wait")
                self.assertEqual(resume(root)["phase"], "ready")
                self.assertIsNone(pause_request(root))

    def test_closed_task_revision_pause_keeps_revision_and_approval_checks(self) -> None:
        for reviewer in (False, True):
            with self.subTest(reviewer=reviewer), self.project(reviewer=reviewer) as root:
                self.make_unavailable(root, "done")
                request_pause(root, reason="goal changed", require_revision=True)
                self.assertIn("Revision to increase", self.assert_resume_refused(root))
                self.write_plan(root, 2, "proposed")
                self.assertIn("must be approved", self.assert_resume_refused(root))
                self.write_plan(root, 2)
                self.assertIn("binds r1", self.assert_resume_refused(root))
                self.write_task(root, "✅ done", revision=2)
                state = resume(root)
                self.assertEqual(state["phase"], "ready")
                self.assertEqual(state["plan_revision"], 2)
                self.assertIsNone(pause_request(root))

    def test_resume_rechecks_task_closed_during_plan_review(self) -> None:
        with self.project(reviewer=True) as root:
            request_pause(root, reason="wait")
            self.write_plan(root, review="unreviewed")
            (harness_dir(root) / "plan-review" / "tasks" / "t1.json").unlink()

            def close_during_review(*args, **kwargs):
                # The reviewer must be able to acquire the lock itself.
                with state_lock(root, wait_seconds=0):
                    self.write_task(root, "✅ done")
                    self.record_review(root)

            with mock.patch("harness.plan_review.run_plan_review", side_effect=close_during_review) as run_review:
                reason = self.assert_resume_refused(root)
                run_review.assert_called_once()
            with self.assertRaises(HarnessError) as caught:
                request_pause(root, reason="wait")
            self.assertEqual(reason, str(caught.exception))
            self.assertIn("task t1", reason)
            self.assertIn("init", reason)
            self.assertIn("successor", reason)


    def test_resume_uses_state_reloaded_after_plan_review(self) -> None:
        with self.project(reviewer=True) as root:
            request_pause(root, reason="wait")
            self.write_plan(root, review="unreviewed")
            (harness_dir(root) / "plan-review" / "tasks" / "t1.json").unlink()
            state_path = harness_dir(root) / "state.json"
            pause_before = (harness_dir(root) / "pause.json").read_bytes()
            changed_state = {}

            def change_current_task(*args, **kwargs):
                with state_lock(root, wait_seconds=0):
                    task = root / ".agent-loop" / "task.md"
                    open_row = task.read_text(encoding="utf-8").splitlines()[-1]
                    self.write_task(root, "✅ done", task_id="t2")
                    task.write_text(task.read_text(encoding="utf-8") + open_row + "\n", encoding="utf-8")
                    self.record_review(root)
                    _, state = load_runtime(root)
                    state["task_id"] = "t2"
                    atomic_write_json(state_path, state)
                    changed_state["bytes"] = state_path.read_bytes()

            with mock.patch("harness.plan_review.run_plan_review", side_effect=change_current_task):
                with self.assertRaises(HarnessError) as caught:
                    resume(root)
            self.assertIn("task t2", str(caught.exception))
            self.assertEqual(state_path.read_bytes(), changed_state["bytes"])
            self.assertEqual((harness_dir(root) / "pause.json").read_bytes(), pause_before)
            with self.assertRaises(HarnessError) as pause_error:
                request_pause(root, reason="wait")
            self.assertEqual(str(caught.exception), str(pause_error.exception))

    def test_resume_uses_pause_request_reloaded_after_plan_review(self) -> None:
        for require_revision in (False, True):
            with self.subTest(require_revision=require_revision), self.project(reviewer=True) as root:
                request_pause(root, reason="wait", require_revision=require_revision)
                self.write_plan(root, 2, "unreviewed")
                self.write_task(root, revision=2)
                (harness_dir(root) / "plan-review" / "tasks" / "t1.json").unlink()
                state_path = harness_dir(root) / "state.json"
                state_before = state_path.read_bytes()
                changed_pause = {}

                def change_pause_kind(*args, **kwargs):
                    with state_lock(root, wait_seconds=0):
                        self.write_task(root, "✅ done", revision=2)
                        self.record_review(root)
                        request = pause_request(root)
                        request["require_revision"] = not require_revision
                        atomic_write_json(harness_dir(root) / "pause.json", request)
                        changed_pause["bytes"] = (harness_dir(root) / "pause.json").read_bytes()

                with mock.patch("harness.plan_review.run_plan_review", side_effect=change_pause_kind):
                    if require_revision:
                        with self.assertRaises(HarnessError) as caught:
                            resume(root)
                        self.assertIn("task t1", str(caught.exception))
                        self.assertIn("successor", str(caught.exception))
                        self.assertEqual(state_path.read_bytes(), state_before)
                        self.assertEqual((harness_dir(root) / "pause.json").read_bytes(), changed_pause["bytes"])
                    else:
                        state = resume(root)
                        self.assertEqual(state["phase"], "ready")
                        self.assertEqual(state["plan_revision"], 2)
                        self.assertIsNone(pause_request(root))


if __name__ == "__main__":
    unittest.main()
