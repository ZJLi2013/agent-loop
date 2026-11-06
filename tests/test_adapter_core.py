from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from adapters.core import handle
from adapters.protocol import HookAction, HookEvent, HookRequest


class AdapterCoreTest(unittest.TestCase):
    def test_tool_event_returns_memory_context(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / ".agent-loop"
            memory = runtime / "memory"
            memory.mkdir(parents=True)
            task = runtime / "task.md"
            task.write_text(
                "## Goal\nship adapter boundary\n\n"
                "| P0 | t1 | r1 | adapter boundary | check | 🔬 doing | 0 |\n",
                encoding="utf-8",
            )
            (memory / "INDEX.md").write_text(
                "- adapter boundary → episodes.md#decisions\n",
                encoding="utf-8",
            )
            (memory / "episodes.md").write_text(
                "- adapter boundary uses canonical events\n",
                encoding="utf-8",
            )

            response = handle(
                HookRequest(
                    event=HookEvent.TOOL_USED,
                    workspace_roots=(Path(directory),),
                    tool_input={"path": str(task)},
                )
            )

        self.assertEqual(response.action, HookAction.CONTEXT)
        self.assertIn("canonical events", response.message or "")

    def test_active_workspace_without_harness_is_blocked(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            runtime = workspace / ".agent-loop"
            runtime.mkdir(parents=True)
            task = runtime / "task.md"
            task.write_text(
                "| P | id | rev | task | check | status | fail |\n"
                "| P0 | t1 | r1 | work | check | 🔬 doing | 0 |\n",
                encoding="utf-8",
            )

            response = handle(
                HookRequest(
                    event=HookEvent.STOP,
                    workspace_roots=(workspace,),
                    status="completed",
                )
            )

        self.assertEqual(response.action, HookAction.CONTINUE)
        self.assertIn("has no Harness state", response.message or "")

if __name__ == "__main__":
    unittest.main()
