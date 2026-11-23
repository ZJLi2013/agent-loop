from __future__ import annotations

import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import uuid
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from harness import compaction
from adapters.core import handle
from adapters.cursor import session_scope
from adapters.protocol import HookEvent, HookRequest
from harness import run
from harness.core import initialize
from harness.plan import pause_request

HOOK = Path(__file__).resolve().parents[1] / "adapters" / "cursor" / "hooks" / "goal-refresh.py"


def _goal_refresh():
    spec = importlib.util.spec_from_file_location("goal_refresh", HOOK)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class CompactionHandoffTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.session = f"test-{uuid.uuid4()}"

    def tearDown(self) -> None:
        self.temp.cleanup()

    def stop_mode(self, env: dict[str, str]) -> str | None:
        request = HookRequest(
            event=HookEvent.STOP,
            workspace_roots=(self.root,),
            status="completed",
            session_id=self.session,
        )
        with mock.patch.dict(os.environ, env, clear=False), mock.patch(
            "adapters.core.completion_gate", return_value=None
        ) as gate:
            handle(request)
        return gate.call_args.args[2]

    def test_pre_compact_marks_the_session_and_its_window(self) -> None:
        env = {"AGENT_LOOP_SESSION_HOST": ""}
        with mock.patch.dict(os.environ, env):
            self.assertIsNone(compaction.handoff_mode(self.session))

            _goal_refresh().output_for(
                json.dumps({"conversation_id": self.session, "workspace_roots": [str(self.root)]})
            )
            self.assertEqual(compaction.handoff_mode(self.session), "new_session")

            _goal_refresh().output_for(
                json.dumps({"conversation_id": self.session, "context_window_size": 300_000})
            )
            self.assertEqual(compaction.handoff_mode(self.session), "new_session_1m")
            self.assertIsNone(compaction.handoff_mode(None))

    def test_only_a_first_compaction_below_1m_notifies_and_none_pauses(self) -> None:
        initialize(self.root, task_id="t1", verifier_argv=[sys.executable, "-S", "-c", "print('OK')"])
        task = self.root / ".agent-loop" / "task.md"
        task.parent.mkdir()
        task.write_text("# Tasks\n", encoding="utf-8")
        payload = {"conversation_id": self.session, "workspace_roots": [str(self.root)]}
        cases = ((300_000, True, True), (compaction.LARGE_CONTEXT_WINDOW, True, False), (300_000, False, False))
        with mock.patch.object(session_scope, "_SCOPES", self.root / "session-cache"):
            session_scope.bind({**payload, "tool_input": {"path": str(task)}})
            for window, first, notifies in cases:
                with self.subTest(window=window, first=first):
                    output = json.loads(_goal_refresh().output_for(
                        json.dumps({**payload, "context_window_size": window, "is_first_compaction": first})
                    ))
                    self.assertEqual(bool(output.get("user_message")), notifies)
                    self.assertIsNone(pause_request(self.root))
        with self.subTest("without a harness"), tempfile.TemporaryDirectory() as bare:
            output = json.loads(_goal_refresh().output_for(
                json.dumps({"workspace_roots": [bare], "context_window_size": 300_000, "is_first_compaction": True})
            ))
            self.assertTrue(output.get("user_message"))

    def test_stop_passes_the_handoff_mode_to_the_gate(self) -> None:
        env = {"AGENT_LOOP_SESSION_HOST": ""}
        self.assertIsNone(self.stop_mode(env))

        compaction.record_compaction(self.session, compaction.LARGE_CONTEXT_WINDOW)
        self.assertEqual(self.stop_mode(env), "new_session")
        compaction.record_compaction(self.session, 300_000)
        self.assertEqual(self.stop_mode(env), "new_session_1m")
        self.assertEqual(self.stop_mode({"AGENT_LOOP_SESSION_HOST": "1"}), "host")

    def verify_payload(self, host: str) -> dict[str, object]:
        env = {
            "AGENT_LOOP_SESSION_HOST": host,
            "AGENT_LOOP_SESSION_ID": "",
            "CURSOR_CONVERSATION_ID": self.session,
        }
        out = io.StringIO()
        with mock.patch.dict(os.environ, env), redirect_stdout(out):
            run.main(["--root", str(self.root), "verify"])
        return json.loads(out.getvalue())

    def test_verify_hands_off_by_the_session_mode(self) -> None:
        cases = (
            ("", None, []),
            ("1", None, ["no reviewer is configured", "End your turn"]),
            ("", 300_000, ["in a new session", "pick a 1M-context model",
                           "Do not initialize another task in this session"]),
        )
        for host, window, expected in cases:
            with self.subTest(host=host, window=window):
                self.tearDown()
                self.setUp()
                initialize(self.root, task_id="t1", verifier_argv=[sys.executable, "-S", "-c", "print('OK')"])
                if window:
                    compaction.record_compaction(self.session, window)
                payload = self.verify_payload(host)
                if not expected:
                    self.assertNotIn("handoff", payload)
                for text in expected:
                    self.assertIn(text, str(payload.get("handoff")))


if __name__ == "__main__":
    unittest.main()
