from __future__ import annotations

import importlib.util
import json
import os
import tempfile
import unittest
import uuid
from pathlib import Path
from unittest import mock

from adapters import compaction
from adapters.core import handle
from adapters.protocol import HookEvent, HookRequest

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

    def test_pre_compact_marks_the_session_without_a_harness(self) -> None:
        self.assertFalse(compaction.compacted(self.session))

        _goal_refresh().output_for(
            json.dumps({"conversation_id": self.session, "workspace_roots": [str(self.root)]})
        )

        self.assertTrue(compaction.compacted(self.session))
        self.assertFalse(compaction.compacted(None))

    def test_stop_passes_the_handoff_mode_to_the_gate(self) -> None:
        env = {"AGENT_LOOP_SESSION_HOST": ""}
        self.assertIsNone(self.stop_mode(env))

        compaction.record_compaction(self.session)
        self.assertEqual(self.stop_mode(env), "new_session")
        self.assertEqual(self.stop_mode({"AGENT_LOOP_SESSION_HOST": "1"}), "host")


if __name__ == "__main__":
    unittest.main()
