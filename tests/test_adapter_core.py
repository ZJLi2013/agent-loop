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

    def test_unrelated_tool_event_is_allowed(self) -> None:
        response = handle(
            HookRequest(
                event=HookEvent.TOOL_USED,
                workspace_roots=(),
                tool_input={"path": "README.md"},
            )
        )

        self.assertEqual(response.action, HookAction.ALLOW)

    def test_legacy_cursor_memory_remains_readable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            runtime = Path(directory) / ".cursor"
            memory = runtime / "memory"
            memory.mkdir(parents=True)
            task = runtime / "task.md"
            task.write_text("## Goal\nlegacy project\n", encoding="utf-8")
            (memory / "INDEX.md").write_text("- legacy decision\n", encoding="utf-8")

            response = handle(
                HookRequest(
                    event=HookEvent.TOOL_USED,
                    workspace_roots=(Path(directory),),
                    tool_input={"path": str(task)},
                )
            )

        self.assertEqual(response.action, HookAction.CONTEXT)
        self.assertIn("legacy decision", response.message or "")


if __name__ == "__main__":
    unittest.main()
