from __future__ import annotations

import importlib.util
import json
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
    def test_first_small_context_compaction_notifies_without_pausing(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(
                root,
                task_id="t1",
                verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
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
                output = json.loads(
                    HOOK.output_for(
                        json.dumps(
                            {
                                "conversation_id": "active",
                                "workspace_roots": [str(root)],
                                "context_window_size": 300_000,
                                "is_first_compaction": True,
                            }
                        )
                    )
                )
                request = pause_request(root)

        self.assertIsNone(request)
        self.assertIn("Context compacted at 300,000 tokens", output["user_message"])
        self.assertIn("cannot switch", output["user_message"])
        self.assertIn("1M-context model", output["user_message"])

    def test_large_context_does_not_notify_user(self) -> None:
        payload = json.dumps(
            {
                "context_window_size": HOOK.LARGE_CONTEXT_WINDOW,
                "is_first_compaction": True,
            }
        )
        with patch.object(HOOK, "has_active_harness", return_value=True):
            output = json.loads(HOOK.output_for(payload))

        self.assertEqual(output, {})

    def test_later_compaction_does_not_notify_user(self) -> None:
        payload = json.dumps(
            {
                "context_window_size": 300_000,
                "is_first_compaction": False,
            }
        )
        with patch.object(HOOK, "has_active_harness", return_value=True):
            output = json.loads(HOOK.output_for(payload))

        self.assertEqual(output, {})

    def test_compact_leaves_other_sessions_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(
                root,
                task_id="t1",
                verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
            )
            state_path = root / ".harness" / "state.json"
            state = json.loads(state_path.read_text(encoding="utf-8"))
            state["owner"] = "A"
            state_path.write_text(json.dumps(state), encoding="utf-8")
            task = root / ".agent-loop" / "task.md"
            task.parent.mkdir(parents=True)
            task.write_text("# Tasks\n", encoding="utf-8")
            payload = {
                "conversation_id": "B",
                "workspace_roots": [str(root)],
                "tool_input": {"path": str(task)},
            }
            with patch.object(
                session_scope, "_SCOPES", root / "session-cache"
            ):
                session_scope.bind(payload)
                output = json.loads(
                    HOOK.output_for(
                        json.dumps(
                            {
                                "conversation_id": "B",
                                "workspace_roots": [str(root)],
                                "context_window_size": 300_000,
                                "is_first_compaction": True,
                            }
                        )
                    )
                )
                request = pause_request(root)

        self.assertEqual(output, {})
        self.assertIsNone(request)


if __name__ == "__main__":
    unittest.main()
