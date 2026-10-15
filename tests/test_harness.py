from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

from harness.core import (
    HarnessError,
    completion_gate,
    disable,
    harness_dir,
    initialize,
    load_runtime,
    run_command,
    verify,
    workspace_fingerprint,
)
from harness.storage import state_lock


def in_background(call, ready) -> "threading.Thread":
    worker = threading.Thread(target=call)
    worker.start()
    deadline = time.monotonic() + 20
    while not ready():
        if time.monotonic() > deadline or not worker.is_alive():
            raise AssertionError("background run did not start")
        time.sleep(0.05)
    return worker


class HarnessTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self) -> None:
        self.temp.cleanup()

    def init(self, code: str = "print('OK')", **kwargs: object) -> None:
        initialize(
            self.root,
            task_id="t1",
            verifier_argv=[sys.executable, "-S", "-c", code],
            **kwargs,
        )

    def test_verify_pass_records_evidence_and_fingerprint(self) -> None:
        self.init()
        result = verify(self.root)
        _, state = load_runtime(self.root)

        self.assertEqual(result["outcome"], "pass")
        self.assertEqual(state["phase"], "verified")
        self.assertTrue(state["verified_fingerprint"])
        run_dir = harness_dir(self.root) / "artifacts" / result["run_id"]
        self.assertEqual((run_dir / "stdout.log").read_text().strip(), "OK")
        self.assertTrue((run_dir / "result.json").exists())
        self.assertEqual(
            len((harness_dir(self.root) / "runs.jsonl").read_text().splitlines()),
            1,
        )

    def test_status_and_gate_work_while_a_command_runs(self) -> None:
        self.init()
        worker = in_background(
            lambda: run_command(
                self.root, [sys.executable, "-S", "-c", "import time; time.sleep(2)"], kind="exec"
            ),
            lambda: (harness_dir(self.root) / "state.json").exists()
            and load_runtime(self.root)[1]["phase"] == "running",
        )

        self.assertIn("is in progress", completion_gate(self.root) or "")
        with self.assertRaisesRegex(HarnessError, "is in progress"):
            run_command(self.root, [sys.executable, "-S", "-c", "pass"], kind="exec")
        worker.join()

        self.assertEqual(load_runtime(self.root)[1]["phase"], "ready")
        self.assertEqual(
            len((harness_dir(self.root) / "runs.jsonl").read_text().splitlines()), 1
        )

    def test_timeout_kills_run_and_stops_at_budget(self) -> None:
        self.init(
            "import time; time.sleep(10)",
            timeout_seconds=0.1,
            max_attempts=1,
        )
        result = verify(self.root)
        _, state = load_runtime(self.root)

        self.assertTrue(result["timed_out"])
        self.assertEqual(result["outcome"], "timeout")
        self.assertEqual(state["phase"], "stopped")

    def test_output_is_redacted_and_bounded(self) -> None:
        self.init(max_output_bytes=100)
        result = run_command(
            self.root,
            [
                sys.executable,
                "-S",
                "-c",
                "print('token=do-not-store ' + 'x' * 1000)",
            ],
            kind="exec",
        )
        output = (
            harness_dir(self.root)
            / "artifacts"
            / result["run_id"]
            / "stdout.log"
        ).read_text()

        self.assertNotIn("do-not-store", output)
        self.assertIn("***REDACTED***", output)
        self.assertTrue(result["stdout_truncated"])
        self.assertLess(len(output.encode()), 200)

    def test_config_drift_is_rejected(self) -> None:
        self.init()
        config_path = harness_dir(self.root) / "config.json"
        config = json.loads(config_path.read_text())
        config["verifier"]["argv"] = [sys.executable, "-S", "-c", "print('changed')"]
        config_path.write_text(json.dumps(config))

        with self.assertRaisesRegex(HarnessError, "changed after init"):
            verify(self.root)
        state = disable(self.root)
        self.assertFalse(state["active"])

    def test_completion_gate_requires_fresh_verification(self) -> None:
        self.init()
        self.assertIn("not independently verified", completion_gate(self.root) or "")

        verify(self.root)
        self.assertIsNone(completion_gate(self.root))

        (self.root / "changed.py").write_text("changed = True\n")
        self.assertIn("is stale", completion_gate(self.root) or "")
        _, state = load_runtime(self.root)
        self.assertEqual(state["phase"], "paused")

    def test_completion_gate_requests_one_stop_report(self) -> None:
        self.init("raise SystemExit(1)", max_attempts=1)
        verify(self.root)

        self.assertIn("Auto-Stop Report", completion_gate(self.root) or "")
        self.assertIsNone(completion_gate(self.root))

    def test_output_contract_can_reject_exit_zero(self) -> None:
        self.init("print('0 tests collected')", expect_regex=r"\bOK\b")
        result = verify(self.root)
        _, state = load_runtime(self.root)

        self.assertEqual(result["outcome"], "reject")
        self.assertFalse(result["verification_passed"])
        self.assertEqual(state["phase"], "paused")
        self.assertEqual(state["last_outcome"], "reject")


class WorkspaceFingerprintTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / "code.py").write_text("x = 1\n")
        self.scratch = self.root / "sub" / ".codex" / "tmp" / "apply_patch"
        self.scratch.parent.mkdir(parents=True)
        self.scratch.write_text("locked\n")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def fingerprint(self) -> str:
        original = Path.open

        def locked_open(path: Path, *args: object, **kwargs: object):
            if ".codex" in path.parts:
                raise OSError("The file cannot be accessed by the system")
            return original(path, *args, **kwargs)

        with mock.patch.object(Path, "open", locked_open):
            return workspace_fingerprint(self.root)

    def assert_scratch_ignored(self) -> None:
        before = self.fingerprint()
        self.scratch.write_text("changed\n")
        self.assertEqual(self.fingerprint(), before)
        (self.root / "code.py").write_text("x = 2\n")
        self.assertNotEqual(self.fingerprint(), before)

    @unittest.skipUnless(shutil.which("git"), "git is required")
    def test_git_path_skips_nested_foreign_runtime(self) -> None:
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]
        for args in (["init", "-q"], ["add", "code.py"], ["commit", "-q", "-m", "init"]):
            subprocess.run(git + args, cwd=self.root, check=True, capture_output=True)

        with mock.patch(
            "harness.fingerprint._fallback_fingerprint",
            side_effect=AssertionError("fell back to the tree walk"),
        ):
            self.assert_scratch_ignored()



class LockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        (self.root / ".harness").mkdir()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def contend(self, content: str) -> str:
        (self.root / ".harness" / "lock").write_text(content, encoding="utf-8")
        with self.assertRaises(HarnessError) as caught:
            with state_lock(self.root, wait_seconds=0.3):
                pass
        return str(caught.exception)

    def test_busy_lock_names_a_live_holder(self) -> None:
        holder = subprocess.Popen([sys.executable, "-S", "-c", "import time; time.sleep(30)"])
        try:
            message = self.contend(
                json.dumps({"pid": holder.pid, "argv": ["harness", "exec"], "started_at": "T0"})
            )
        finally:
            holder.kill()
            holder.wait()

        self.assertIn(f"pid {holder.pid} (harness exec) since T0", message)
        self.assertNotIn("Remove it with", message)

    def test_stale_lock_gives_the_removal_command(self) -> None:
        gone = subprocess.Popen([sys.executable, "-S", "-c", "pass"])
        gone.wait()
        for content in (json.dumps({"pid": gone.pid}), f"{gone.pid}\n"):
            with self.subTest(content=content):
                self.assertIn("Remove it with", self.contend(content))


if __name__ == "__main__":
    unittest.main()
