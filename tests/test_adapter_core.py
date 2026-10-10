from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from adapters.core import handle
from adapters.protocol import HookAction, HookEvent, HookRequest
from harness.core import initialize


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

    def test_canonical_memory_wins_over_legacy_copy(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / ".agent-loop"
            memory = runtime / "memory"
            memory.mkdir(parents=True)
            task = runtime / "task.md"
            task.write_text("## Goal\ncanonical project\n", encoding="utf-8")
            (memory / "INDEX.md").write_text(
                "- canonical decision\n", encoding="utf-8"
            )
            legacy = root / ".cursor" / "memory"
            legacy.mkdir(parents=True)
            (legacy / "INDEX.md").write_text(
                "- stale legacy decision\n", encoding="utf-8"
            )

            response = handle(
                HookRequest(
                    event=HookEvent.TOOL_USED,
                    workspace_roots=(root,),
                    tool_input={"path": str(task)},
                )
            )

        self.assertIn("canonical decision", response.message or "")
        self.assertNotIn("stale legacy decision", response.message or "")

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

    def test_nested_project_is_not_scanned(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            project = workspace / "subproject"
            runtime = project / ".agent-loop"
            runtime.mkdir(parents=True)
            (runtime / "task.md").write_text(
                "| P | id | rev | task | check | status | fail |\n"
                "| P0 | t1 | — | work | check | 🔬 doing | 0 |\n",
                encoding="utf-8",
            )
            initialize(
                project,
                task_id="t1",
                verifier_argv=[sys.executable, "-c", "print('OK')"],
            )

            response = handle(
                HookRequest(
                    event=HookEvent.STOP,
                    workspace_roots=(workspace,),
                    status="completed",
                )
            )

        self.assertEqual(response.action, HookAction.ALLOW)
        self.assertIsNone(response.message)


if __name__ == "__main__":
    unittest.main()
