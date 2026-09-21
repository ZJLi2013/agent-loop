from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from harness.core import initialize

HOOK_PATH = (
    Path(__file__).resolve().parents[1]
    / ".cursor"
    / "hooks"
    / "harness-stop.py"
)
SPEC = importlib.util.spec_from_file_location("harness_stop", HOOK_PATH)
assert SPEC and SPEC.loader
HOOK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HOOK
SPEC.loader.exec_module(HOOK)


class HarnessStopHookTest(unittest.TestCase):
    def test_completed_session_gets_followup_for_active_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(
                root,
                task_id="t1",
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )
            followup = HOOK.followup_for(
                {"status": "completed", "workspace_roots": [str(root)]}
            )

        self.assertIn("not independently verified", followup or "")

    def test_aborted_session_is_not_requeued(self) -> None:
        followup = HOOK.followup_for(
            {"status": "aborted", "workspace_roots": ["C:/unused"]}
        )
        self.assertIsNone(followup)


if __name__ == "__main__":
    unittest.main()

