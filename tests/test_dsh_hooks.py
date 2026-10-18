from __future__ import annotations

import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from harness import run
from harness.core import completion_gate, initialize

HOOKS = Path(__file__).resolve().parents[1] / "adapters" / "dsh" / "hooks"


class DshHooksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name) / "proj"
        self.task = self.root / ".agent-loop" / "task.md"
        self.task.parent.mkdir(parents=True)
        self.task.write_text("# Tasks\n| P1 | g1 | — | probe | ok | 🔬 doing | 0 |\n", encoding="utf-8")
        markers = Path(self.tmp.name) / "markers"
        markers.mkdir()
        self.env = {**os.environ, "TEMP": str(markers), "TMP": str(markers), "TMPDIR": str(markers)}

    def hook(self, name: str, payload: dict[str, object]) -> dict[str, object]:
        result = subprocess.run(
            [sys.executable, str(HOOKS / name)],
            input=json.dumps(payload), capture_output=True, text=True,
            encoding="utf-8", env=self.env, check=True,
        )
        return json.loads(result.stdout)

    def stop(self, session: str) -> dict[str, object]:
        return self.hook("harness-stop.py", {
            "session_id": session, "turn_id": "1", "transcript_path": None,
            "cwd": str(self.root), "hook_event_name": "Stop",
            "model": "DeepSeek-V4.1-Flash", "permission_mode": "default",
            "stop_hook_active": False, "last_assistant_message": None,
        })

    def initialize(self, owner: str | None) -> None:
        initialize(
            self.root, task_id="g1", owner=owner,
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
        )

    def test_stop_blocks_until_the_owning_session_is_verified(self) -> None:
        self.initialize("S")
        expected = completion_gate(self.root, "S")

        blocked = self.stop("S")
        with redirect_stdout(io.StringIO()):
            code = run.main(["--root", str(self.root), "verify"])
        released = self.stop("S")

        self.assertIsNotNone(expected)
        self.assertEqual(blocked, {"decision": "block", "reason": expected})
        self.assertEqual(code, 0)
        self.assertEqual(released, {})

    def test_stop_leaves_another_sessions_task_alone(self) -> None:
        self.initialize("S")

        self.assertEqual(self.stop("other"), {})

    def test_stop_blocks_once_per_message(self) -> None:
        self.initialize(None)

        first = self.stop("S")
        repeated = self.stop("S")

        self.assertEqual(first.get("decision"), "block")
        self.assertEqual(repeated, {})

    def test_stop_without_harness_state_asks_for_init(self) -> None:
        output = self.stop("S")

        self.assertEqual(output.get("decision"), "block")
        self.assertTrue(str(output.get("reason")).startswith("Active task in"))

    def test_session_start_injects_memory_index(self) -> None:
        memory = self.task.parent / "memory"
        memory.mkdir()
        (memory / "INDEX.md").write_text("- facts: gateway\n", encoding="utf-8")

        output = self.hook("memory-lookup.py", {
            "session_id": "S", "cwd": str(self.root), "hook_event_name": "SessionStart",
        })

        specific = output["hookSpecificOutput"]
        self.assertEqual(specific["hookEventName"], "SessionStart")
        self.assertIn("- facts: gateway", specific["additionalContext"])

    def test_session_start_outside_a_project_is_silent(self) -> None:
        output = self.hook("memory-lookup.py", {
            "session_id": "S", "cwd": self.tmp.name, "hook_event_name": "SessionStart",
        })

        self.assertEqual(output, {})


if __name__ == "__main__":
    unittest.main()
