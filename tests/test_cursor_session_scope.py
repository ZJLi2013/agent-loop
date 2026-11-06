from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from adapters.cursor import session_scope


class CursorSessionScopeTest(unittest.TestCase):
    def _payload(
        self,
        conversation_id: str,
        workspace: Path,
        task: Path | None = None,
    ) -> dict[str, object]:
        payload: dict[str, object] = {
            "conversation_id": conversation_id,
            "workspace_roots": [str(workspace)],
        }
        if task is not None:
            payload["tool_input"] = {"path": str(task)}
        return payload

    def _task(self, root: Path) -> Path:
        task = root / ".agent-loop" / "task.md"
        task.parent.mkdir(parents=True)
        task.write_text("# Tasks\n", encoding="utf-8")
        return task

    def test_every_task_read_joins_the_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            first = workspace / "first"
            second = workspace / "second"
            first_task = self._task(first)
            second_task = self._task(second)
            cache = workspace / "cache"
            with patch.object(session_scope, "_SCOPES", cache):
                session_scope.bind(self._payload("one", workspace, first_task))
                session_scope.bind(self._payload("one", workspace, second_task))
                session_scope.bind(self._payload("one", workspace, first_task))
                bound = session_scope.roots(self._payload("one", workspace))

        self.assertEqual(bound, (first.resolve(), second.resolve()))

    def test_a_directory_nested_in_a_project_joins_only_as_its_own_repository(self) -> None:
        for git, joins in ((None, False), ("dir", True), ("file", True)):
            with self.subTest(git=git), tempfile.TemporaryDirectory() as directory:
                project = Path(directory) / "project"
                self._task(project)
                nested = project / "tests" / "fixtures" / "x"
                nested_task = self._task(nested)
                if git == "dir":
                    (nested / ".git").mkdir()
                elif git == "file":
                    (nested / ".git").write_text("gitdir: ../.git/worktrees/x\n", encoding="utf-8")
                cache = Path(directory) / "cache"
                with patch.object(session_scope, "_SCOPES", cache):
                    session_scope.bind(self._payload("one", project, nested_task))
                    bound = session_scope.roots(self._payload("one", project))
                    self.assertEqual(bound, (nested.resolve(),) if joins else ())
                    # A scope file written before the nested check stops binding the fixture too.
                    cache.mkdir(exist_ok=True)
                    session_scope._scope_file(self._payload("one", project)).write_text(
                        f"{nested.resolve()}\n", encoding="utf-8"
                    )
                    bound = session_scope.roots(self._payload("one", project))
                    self.assertEqual(bound, (nested.resolve(),) if joins else ())

if __name__ == "__main__":
    unittest.main()
