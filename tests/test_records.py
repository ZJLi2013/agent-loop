from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from harness.records import (
    _task_sections,
    archive_closed_tasks,
    archived_task_ids,
)


TASKS = """# Tasks

| P | id | rev | task | check | status | fail |
|---|---|---|---|---|---|---|
| P0 | t1 | r1 | finished | check | ✅ done | 0 |
| P0 | t2 | r1 | rejected | check | ❌ dropped | 0 |
| P0 | t3 | r1 | current | check | 🔬 doing | 0 |
"""


class TaskSectionTest(unittest.TestCase):
    def test_headings_inside_fences_do_not_end_section(self) -> None:
        for opening, closing in (("```shell", "```"), ("~~~text", "~~~")):
            with self.subTest(opening=opening):
                lines = [
                    "### s1 design",
                    "text",
                    opening,
                    "# comment inside a fence",
                    closing,
                    "tail of s1",
                    "## Next",
                ]

                self.assertEqual(_task_sections(lines, "s1"), [(0, 6)])

    def test_task_heading_and_anchor_inside_fence_do_not_start_section(self) -> None:
        lines = [
            "```markdown",
            '<a id="s1-fake"></a>',
            "### s1 fake",
            "```",
            "### s1 real",
            "body",
            "## Next",
        ]

        self.assertEqual(_task_sections(lines, "s1"), [(4, 6)])

    def test_shorter_marker_does_not_close_fence(self) -> None:
        lines = [
            "### s1 design",
            "````text",
            "# comment",
            "```",
            "## still fenced",
            "````",
            "tail",
            "## Next",
        ]

        self.assertEqual(_task_sections(lines, "s1"), [(0, 7)])


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

if __name__ == "__main__":
    unittest.main()
