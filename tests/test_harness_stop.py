from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters.cursor import session_scope
from harness.core import initialize

HOOK_PATH = (
    Path(__file__).resolve().parents[1]
    / "adapters"
    / "cursor"
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
            task = root / ".agent-loop" / "task.md"
            task.parent.mkdir(parents=True)
            task.write_text("# Tasks\n", encoding="utf-8")
            initialize(
                root,
                task_id="t1",
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )
            payload = {
                "conversation_id": "active",
                "workspace_roots": [str(root)],
                "tool_input": {"path": str(task)},
            }
            with patch.object(
                session_scope, "_SCOPES", root / "session-cache"
            ), patch(
                "harness.core._remaining_wall", side_effect=[1800.0, 1790.0]
            ):
                session_scope.bind(payload)
                followup = HOOK.followup_for(
                    {
                        "conversation_id": "active",
                        "status": "completed",
                        "workspace_roots": [str(root)],
                    }
                )
                repeated = HOOK.followup_for(
                    {
                        "conversation_id": "active",
                        "status": "completed",
                        "workspace_roots": [str(root)],
                    }
                )

        self.assertIn("not independently verified", followup or "")
        self.assertIsNone(repeated)

    def test_unbound_session_is_not_requeued(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            initialize(
                root,
                task_id="t1",
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )
            with patch.object(
                session_scope, "_SCOPES", root / "session-cache"
            ):
                followup = HOOK.followup_for(
                    {
                        "conversation_id": "unbound",
                        "status": "completed",
                        "workspace_roots": [str(root)],
                    }
                )

        self.assertIsNone(followup)

    def test_aborted_session_is_not_requeued(self) -> None:
        followup = HOOK.followup_for(
            {"status": "aborted", "workspace_roots": ["C:/unused"]}
        )
        self.assertIsNone(followup)


if __name__ == "__main__":
    unittest.main()

