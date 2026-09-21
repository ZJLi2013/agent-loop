from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from harness.core import initialize
from harness.plan import pause_request

HOOK_PATH = (
    Path(__file__).resolve().parents[1]
    / ".cursor"
    / "hooks"
    / "goal-refresh.py"
)
SPEC = importlib.util.spec_from_file_location("goal_refresh", HOOK_PATH)
assert SPEC and SPEC.loader
HOOK = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = HOOK
SPEC.loader.exec_module(HOOK)


class GoalRefreshHookTest(unittest.TestCase):
    def test_pre_compact_requests_goal_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(
                root,
                task_id="t1",
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )
            count = HOOK.request_for({"workspace_roots": [str(root)]})
            request = pause_request(root)

        self.assertEqual(count, 1)
        self.assertEqual(request["kind"], "goal_review")
        self.assertIn("context compacted", request["reason"])

    def test_inactive_workspace_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            count = HOOK.request_for({"workspace_roots": [directory]})
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()

