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

    def test_every_worktree_of_a_clone_reads_one_memory_in_the_git_directory(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            main = Path(directory) / "main"
            linked = Path(directory) / "linked"
            main.mkdir()

            def git(*args: str) -> None:
                subprocess.run(["git", *args], cwd=main, check=True, capture_output=True)

            def read_task(root: Path) -> str:
                task = root / ".agent-loop" / "task.md"
                task.parent.mkdir(parents=True, exist_ok=True)
                task.write_text("## Goal\ng\n", encoding="utf-8")
                response = handle(
                    HookRequest(event=HookEvent.TOOL_USED, workspace_roots=(root,), tool_input={"path": str(task)})
                )
                return response.message or ""

            git("init", "-q")
            git("-c", "user.name=t", "-c", "user.email=t@example.com", "commit", "-q", "--allow-empty", "-m", "init")
            git("worktree", "add", "-q", str(linked))
            memory = (main / ".git" / "agent-loop" / "memory").resolve()
            memory.mkdir(parents=True)
            (memory / "INDEX.md").write_text("- shared fact\n", encoding="utf-8")
            (linked / ".agent-loop" / "memory").mkdir(parents=True)

            self.assertEqual(memory_dir(main), memory)
            self.assertEqual(memory_dir(linked), memory)
            message = read_task(linked)
            self.assertIn("shared fact", message)
            self.assertIn(str(memory), message)
            self.assertIn("不再被读取", message)

            broken = Path(directory) / "broken"
            broken.mkdir()
            (broken / ".git").write_text("gitdir: missing/worktree\n", encoding="utf-8")
            self.assertIn("找不到本项目的 memory", read_task(broken))

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
