from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.records import archive_closed_tasks, archived_task_ids


TASKS = """# Tasks

| P | id | rev | task | check | status | fail |
|---|---|---|---|---|---|---|
| P0 | t1 | r1 | finished | check | ✅ done | 0 |
| P0 | t2 | r1 | rejected | check | ❌ dropped | 0 |
| P0 | t3 | r1 | current | check | 🔬 doing | 0 |
"""


class RecordLifecycleTest(unittest.TestCase):
    def test_closed_tasks_leave_active_backlog_and_remain_retrievable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / ".agent-loop"
            runtime.mkdir()
            task = runtime / "task.md"
            task.write_text(TASKS, encoding="utf-8")

            moved = archive_closed_tasks(root)
            active = task.read_text(encoding="utf-8")
            archive = (runtime / "archive" / "tasks.md").read_text(
                encoding="utf-8"
            )

            self.assertEqual(moved, ["t1", "t2"])
            self.assertNotIn("| t1 |", active)
            self.assertNotIn("| t2 |", active)
            self.assertIn("| t3 |", active)
            self.assertIn("archive/tasks.md", active)
            self.assertIn("| t1 |", archive)
            self.assertIn("| t2 |", archive)
            self.assertEqual(archived_task_ids(root), {"t1", "t2"})

    def test_archiving_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / ".agent-loop"
            runtime.mkdir()
            task = runtime / "task.md"
            task.write_text(TASKS, encoding="utf-8")

            archive_closed_tasks(root)
            before = (runtime / "archive" / "tasks.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(archive_closed_tasks(root), [])
            after = (runtime / "archive" / "tasks.md").read_text(
                encoding="utf-8"
            )

            self.assertEqual(after, before)

    def test_reused_task_id_from_previous_goal_is_still_archived(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            runtime = root / ".agent-loop"
            (runtime / "archive").mkdir(parents=True)
            old_row = "| P0 | t1 | r1 | previous goal | check | ✅ done | 0 |"
            (runtime / "archive" / "tasks.md").write_text(
                "# Closed Tasks\n\n"
                "| P | id | rev | task | check | status | fail |\n"
                "|---|---|---|---|---|---|---|\n"
                f"{old_row}\n",
                encoding="utf-8",
            )
            (runtime / "task.md").write_text(TASKS, encoding="utf-8")

            archive_closed_tasks(root)
            archive = (runtime / "archive" / "tasks.md").read_text(
                encoding="utf-8"
            )

            self.assertIn(old_row, archive)
            self.assertIn("| t1 | r1 | finished |", archive)


if __name__ == "__main__":
    unittest.main()
