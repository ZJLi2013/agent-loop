from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters.cursor import session_scope
from harness.core import initialize
from harness.plan import pause_request

HOOK_PATH = (
    Path(__file__).resolve().parents[1]
    / "adapters"
    / "cursor"
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
            task = root / ".agent-loop" / "task.md"
            task.parent.mkdir(parents=True)
            task.write_text("# Tasks\n", encoding="utf-8")
            payload = {
                "conversation_id": "active",
                "workspace_roots": [str(root)],
                "tool_input": {"path": str(task)},
            }
            with patch.object(
                session_scope, "_SCOPES", root / "session-cache"
            ):
                session_scope.bind(payload)
                count = HOOK.request_for(
                    {
                        "conversation_id": "active",
                        "workspace_roots": [str(root)],
                    }
                )
                request = pause_request(root)

        self.assertEqual(count, 1)
        self.assertEqual(request["kind"], "goal_review")
        self.assertIn("context compacted", request["reason"])

    def test_inactive_workspace_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            count = HOOK.request_for({"workspace_roots": [directory]})
        self.assertEqual(count, 0)

    def test_compact_only_pauses_the_bound_project(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            project = workspace / "first"
            other = workspace / "second"
            initialize(
                project,
                task_id="t1",
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )
            initialize(
                other,
                task_id="t2",
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )
            task = project / ".agent-loop" / "task.md"
            task.parent.mkdir(parents=True)
            task.write_text("# Tasks\n", encoding="utf-8")
            payload = {
                "conversation_id": "first",
                "workspace_roots": [directory],
                "tool_input": {"path": str(task)},
            }
            with patch.object(
                session_scope, "_SCOPES", workspace / "session-cache"
            ):
                session_scope.bind(payload)
                count = HOOK.request_for(
                    {
                        "conversation_id": "first",
                        "workspace_roots": [directory],
                    }
                )
                request = pause_request(project)
                other_request = pause_request(other)

        self.assertEqual(count, 1)
        self.assertIsNotNone(request)
        self.assertIsNone(other_request)


if __name__ == "__main__":
    unittest.main()

