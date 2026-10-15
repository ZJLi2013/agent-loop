from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from adapters.core import request_goal_review
from adapters.cursor import session_scope
from harness import run
from harness.core import completion_gate, initialize
from harness.plan import pause_request

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

    def stop_with_goal_review_due(
        self, root: Path, *, owner: str | None, session: str
    ) -> tuple[str | None, bytes, bytes]:
        task = root / ".agent-loop" / "task.md"
        task.parent.mkdir(parents=True)
        task.write_text("# Tasks\n", encoding="utf-8")
        initialize(
            root,
            task_id="t1",
            verifier_argv=[sys.executable, "-c", "print('OK')"],
        )
        state_path = root / ".harness" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["last_goal_review_at"] = "2000-01-01T00:00:00+00:00"
        if owner is not None:
            state["owner"] = owner
        state_path.write_text(json.dumps(state), encoding="utf-8")
        before = state_path.read_bytes()
        with patch.object(session_scope, "_SCOPES", root / "session-cache"):
            session_scope.bind(
                {
                    "conversation_id": session,
                    "workspace_roots": [str(root)],
                    "tool_input": {"path": str(task)},
                }
            )
            followup = HOOK.followup_for(
                {
                    "conversation_id": session,
                    "status": "completed",
                    "workspace_roots": [str(root)],
                }
            )
        return followup, before, state_path.read_bytes()

    def test_other_sessions_task_is_left_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            followup, before, after = self.stop_with_goal_review_due(
                root, owner="A", session="B"
            )
            paused = (root / ".harness" / "pause.json").exists()

        self.assertIsNone(followup)
        self.assertEqual(before, after)
        self.assertFalse(paused)

    def test_owning_session_gets_goal_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            followup, _, _ = self.stop_with_goal_review_due(
                Path(directory), owner="A", session="A"
            )

        self.assertIn("Goal Review", followup or "")

    def test_task_without_owner_gets_goal_review(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            followup, _, _ = self.stop_with_goal_review_due(
                Path(directory), owner=None, session="B"
            )

        self.assertIn("Goal Review", followup or "")

    def owned_task_with_goal_review_due(self, root: Path) -> Path:
        initialize(
            root,
            task_id="t1",
            verifier_argv=[sys.executable, "-c", "print('OK')"],
            owner="A",
        )
        state_path = root / ".harness" / "state.json"
        state = json.loads(state_path.read_text(encoding="utf-8"))
        state["last_goal_review_at"] = "2000-01-01T00:00:00+00:00"
        state_path.write_text(json.dumps(state), encoding="utf-8")
        return state_path

    def test_gate_without_session_leaves_owned_task_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            state_path = self.owned_task_with_goal_review_due(root)
            before = state_path.read_bytes()

            message = completion_gate(root)

            self.assertIsNone(message)
            self.assertEqual(state_path.read_bytes(), before)

    def test_compact_without_session_leaves_owned_task_alone(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.owned_task_with_goal_review_due(root)

            self.assertEqual(request_goal_review((root,)), 0)
            self.assertIsNone(pause_request(root))

    def test_cli_init_records_session_as_owner(self) -> None:
        cases = (
            ({"AGENT_LOOP_SESSION_ID": "own", "CURSOR_CONVERSATION_ID": "c"}, "own"),
            ({"CURSOR_CONVERSATION_ID": "c"}, "c"),
            ({}, None),
        )
        base = {
            key: value
            for key, value in os.environ.items()
            if key not in {"AGENT_LOOP_SESSION_ID", "CURSOR_CONVERSATION_ID"}
        }
        for env, owner in cases:
            with self.subTest(env=env), tempfile.TemporaryDirectory() as directory:
                with patch.dict(os.environ, {**base, **env}, clear=True), redirect_stdout(
                    io.StringIO()
                ):
                    code = run.main(
                        ["--root", directory, "init", "--task", "t1", "--",
                         sys.executable, "-c", "print('OK')"]
                    )
                state = json.loads(
                    (Path(directory) / ".harness" / "state.json").read_text(
                        encoding="utf-8"
                    )
                )

                self.assertEqual(code, 0)
                self.assertEqual(state.get("owner"), owner)


if __name__ == "__main__":
    unittest.main()

