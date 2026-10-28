from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from adapters.core import SHARED_MEMORY_ENV, arrivals_file, handle
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

    def test_shared_memory_index_is_injected_on_every_task_read(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            shared = base / "shared"
            shared.mkdir()
            (shared / "INDEX.md").write_text("- render backends → render.md\n", encoding="utf-8")
            home = base / "home"
            env = {"HOME": str(home), "USERPROFILE": str(home), SHARED_MEMORY_ENV: str(shared)}

            def read_task(project: Path, with_memory: bool, path: str | None = None) -> str:
                runtime = project / ".agent-loop"
                runtime.mkdir(parents=True, exist_ok=True)
                if with_memory:
                    (runtime / "memory").mkdir(exist_ok=True)
                    (runtime / "memory" / "INDEX.md").write_text("- local\n", encoding="utf-8")
                task = runtime / "task.md"
                task.write_text(
                    "## Goal\ng\n\n| P0 | t1 | r2 | work | check | 🔬 doing | 0 |\n",
                    encoding="utf-8",
                )
                response = handle(HookRequest(
                    event=HookEvent.TOOL_USED,
                    workspace_roots=(project,),
                    tool_input={"path": path or str(task)},
                ))
                return response.message or ""

            def arrivals() -> list[dict[str, str]]:
                path = arrivals_file()
                if not path.is_file():
                    return []
                return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

            with mock.patch.dict(os.environ, env):
                with self.subTest("project memory present"):
                    message = read_task(base / "a", with_memory=True)
                    self.assertIn("- local", message)
                    self.assertIn("render backends", message)
                with self.subTest("project memory missing"):
                    message = read_task(base / "b", with_memory=False)
                    self.assertIn("agent-memory", message)
                    self.assertIn("render backends", message)
                with self.subTest("re-read injects the current index and logs each arrival"):
                    (shared / "INDEX.md").write_text("- render backends → render-v2.md\n", encoding="utf-8")
                    self.assertIn("render-v2.md", read_task(base / "a", with_memory=True))
                    logged = arrivals()
                    self.assertEqual(len(logged), 3)
                    self.assertEqual(logged[0]["task"], "t1@r2")
                    self.assertEqual(Path(logged[1]["project"]), (base / "b").resolve())
                with self.subTest("one project key however the path is spelled"):
                    project = base / "c"
                    absolute = str(project / ".agent-loop" / "task.md")
                    spellings = [absolute, ".agent-loop/task.md"]
                    if os.name == "nt":
                        spellings.append(absolute[0].swapcase() + absolute[1:])
                    for spelling in spellings:
                        read_task(project, with_memory=False, path=spelling)
                    keys = {entry["project"] for entry in arrivals()[3:]}
                    self.assertEqual(len(keys), 1, keys)
                with self.subTest("unset variable leaves project memory alone"):
                    count = len(arrivals())
                    with mock.patch.dict(os.environ, {SHARED_MEMORY_ENV: ""}):
                        message = read_task(base / "a", with_memory=True)
                    self.assertNotIn("render backends", message)
                    self.assertEqual(len(arrivals()), count)

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
