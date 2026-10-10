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

    def test_conversations_bind_different_nested_projects(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            first = workspace / "first"
            second = workspace / "second"
            first_task = self._task(first)
            second_task = self._task(second)
            cache = workspace / "cache"
            with patch.object(session_scope, "_SCOPES", cache):
                session_scope.bind(self._payload("one", workspace, first_task))
                session_scope.bind(self._payload("two", workspace, second_task))

                first_roots = session_scope.roots(
                    self._payload("one", workspace)
                )
                second_roots = session_scope.roots(
                    self._payload("two", workspace)
                )

        self.assertEqual(first_roots, (first.resolve(),))
        self.assertEqual(second_roots, (second.resolve(),))

    def test_first_task_read_owns_the_conversation(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            workspace = Path(directory)
            first = workspace / "first"
            second = workspace / "second"
            first_task = self._task(first)
            second_task = self._task(second)
            cache = workspace / "cache"
            with patch.object(session_scope, "_SCOPES", cache):
                payload = self._payload("one", workspace, first_task)
                session_scope.bind(payload)
                rebound = session_scope.bind(
                    self._payload("one", workspace, second_task)
                )

        self.assertEqual(rebound, first.resolve())

if __name__ == "__main__":
    unittest.main()
