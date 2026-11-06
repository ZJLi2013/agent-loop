from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

from adapters.core import handle
from adapters.protocol import HookAction, HookEvent, HookRequest
from harness.project import memory_dir


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

    def test_linked_worktree_reads_the_main_worktree_memory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            main = Path(directory) / "main"
            linked = Path(directory) / "linked"
            main.mkdir()

            def git(*args: str) -> None:
                subprocess.run(["git", *args], cwd=main, check=True, capture_output=True)

            git("init", "-q")
            git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", "init")
            git("worktree", "add", "-q", str(linked))
            memory = main / ".agent-loop" / "memory"
            memory.mkdir(parents=True)
            (memory / "INDEX.md").write_text("- shared fact\n", encoding="utf-8")
            (linked / ".agent-loop" / "memory").mkdir(parents=True)
            task = linked / ".agent-loop" / "task.md"
            task.write_text("## Goal\ng\n", encoding="utf-8")

            self.assertEqual(memory_dir(main), memory.resolve())
            self.assertEqual(memory_dir(linked), memory.resolve())
            response = handle(
                HookRequest(
                    event=HookEvent.TOOL_USED,
                    workspace_roots=(linked,),
                    tool_input={"path": str(task)},
                )
            )

        self.assertIn("shared fact", response.message or "")
        self.assertIn("不再被读取", response.message or "")

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
