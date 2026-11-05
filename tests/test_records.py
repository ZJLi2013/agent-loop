from __future__ import annotations

import json
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from harness import records
from harness.core import initialize
from harness.errors import HarnessError
from harness.records import (
    _task_sections,
    archive_closed_tasks,
    archive_progress,
    archived_task_ids,
    close_task,
    design_location_error,
    leftovers,
)
from harness.storage import config_digest


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


DESIGN_PLAN = """# Plan

Plan Revision: 1
Plan Review: approved

### Data cleanup (a1)
topic design

### a1 result
result

### a1 Data cleanup
id design

### Workspace (a1, a2)
shared design

<a id="a1-plan"></a>
### a1 计划（草）
anchored design
"""


class DesignLocationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / ".agent-loop"
        (self.runtime / "plans" / "x" / "sub-exp").mkdir(parents=True)
        (self.runtime / "plans" / "x" / "plan.md").write_text(DESIGN_PLAN, encoding="utf-8")
        (self.runtime / "plans" / "x" / "sub-exp" / "a1.md").write_text("design\n", encoding="utf-8")
        scratch = self.root / ".harness" / "tasks" / "a1"
        scratch.mkdir(parents=True)
        (scratch / "design.md").write_text("design\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def link(self, target: str) -> None:
        (self.runtime / "task.md").write_text(
            "| P | id | rev | task | check | status | fail |\n|---|---|---|---|---|---|---|\n"
            f"| P0 | a1 | r1 | clean | [设计]({target})；通过 | 🔬 doing | 0 |\n",
            encoding="utf-8",
        )

    def test_only_links_close_can_retire_locate_a_design(self) -> None:
        cases = (
            ("topic heading beside a result section", "plans/x/plan.md#data-cleanup-a1", False),
            ("heading starting with the id", "plans/x/plan.md#a1-data-cleanup", True),
            ("plan without anchor", "plans/x/plan.md", False),
            ("shared heading", "plans/x/plan.md#workspace-a1-a2", False),
            ("explicit anchor", "plans/x/plan.md#a1-plan", True),
            ("sub-exp file", "plans/x/sub-exp/a1.md", True),
            ("task scratch", "../.harness/tasks/a1/design.md", False),
            ("missing file", "plans/x/sub-exp/missing.md", False),
        )
        for name, target, located in cases:
            with self.subTest(name):
                self.link(target)
                error = design_location_error(self.root, "a1", ".agent-loop/plans/x/plan.md")
                self.assertEqual(error is None, located, error)

    def test_init_refuses_the_topic_layout_and_close_retires_the_fixed_one(self) -> None:
        plan_doc = ".agent-loop/plans/x/plan.md"
        self.link("plans/x/plan.md#data-cleanup-a1")
        with self.assertRaisesRegex(HarnessError, "CLOSE archives only those"):
            initialize(
                self.root, task_id="a1", plan_doc=plan_doc,
                verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
            )

        self.link("plans/x/plan.md#a1-data-cleanup")
        self.assertIsNone(design_location_error(self.root, "a1", plan_doc))
        close_task(self.root, plan_doc, "a1", None)
        plan = (self.root / plan_doc).read_text(encoding="utf-8")
        archive = (self.runtime / "plans" / "x" / "plan-archive.md").read_text(encoding="utf-8")
        self.assertNotIn("id design", plan)
        self.assertIn("id design", archive)


LEFTOVER_TASKS = """# Tasks

## 主线

Mainline Review: approved

| Goal | 问题 | 退出条件 | 状态 | plan |
|---|---|---|---|---|
| A | a | a | ✅ done | [plan](plans/a/plan.md) |
| B | b | b | ▶ next | [plan](plans/b/plan.md) |

## Goal

| P | id | rev | task | check | status | fail |
|---|---|---|---|---|---|---|
| P0 | t11 | r1 | [设计](plans/b/plan.md#t11) | check | 🔬 doing | 0 |
| P0 | t4 | r1 | reopened | check | ⬜ todo | 0 |
"""

ARCHIVED = """| P | id | rev | task | check | status | fail |
|---|---|---|---|---|---|---|
| P0 | t1 | r1 | a | check | ✅ done | 0 |
| P0 | t3 | r1 | a | check | ✅ done | 0 |
| P0 | t4 | r1 | a | check | ✅ done | 0 |
| P0 | p2 | r1 | a | check | ✅ done | 0 |
"""

PROGRESS = """# Progress

## 11-04 newest
`keep_t3.py` is still in use.

## 11-03 older
```text
## not a heading
```
`verify_t3.py` passed.

## 11-02 oldest
done
"""


class LeftoversTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.runtime = self.root / ".agent-loop"
        files = {
            "task.md": LEFTOVER_TASKS,
            "archive/tasks.md": ARCHIVED,
            "progress.md": PROGRESS,
            "memory/facts.md": "facts\n",
            "memory/verify_t3_notes.md": "notes\n",
            "verify_t3.py": "",
            "keep_t3.py": "",
            "verify_g7p2.py": "",
            "verify_t11.py": "",
            "verify_t4.py": "",
            "verify_t1.py": "",
            "plans/a/plan.md": "`verify_t1.py`\n",
            "plans/a/plan-archive.md": "",
            "plans/a/sub-exp/t3.md": "",
            "plans/a/replay.json": "",
            "plans/a/cache/x_t3.pyc": "",
            "plans/a/cache/y.pyc": "",
            "plans/b/plan.md": "copy `verify_t1.py` for t11\n",
        }
        for name, text in files.items():
            path = self.runtime / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def test_reports_closed_entries_that_no_current_document_mentions(self) -> None:
        self.assertEqual(
            leftovers(self.root),
            [
                {"path": ".agent-loop/plans/a/cache/", "why": "closed Goal plan plans/a/plan.md, closed task t3"},
                {"path": ".agent-loop/plans/a/replay.json", "why": "closed Goal plan plans/a/plan.md"},
                {"path": ".agent-loop/verify_g7p2.py", "why": "closed task p2"},
                {"path": ".agent-loop/verify_t3.py", "why": "closed task t3"},
            ],
        )

    def test_active_harness_keeps_its_locked_verifier_out(self) -> None:
        config = {"verifier": {"files": {".agent-loop/plans/a/cache/y.pyc": "digest"}}}
        reported = {
            True: {".agent-loop/plans/a/cache/x_t3.pyc"},
            False: {".agent-loop/plans/a/cache/"},
        }
        base = self.root / ".harness"
        base.mkdir()
        (base / "config.json").write_text(json.dumps(config), encoding="utf-8")
        for active, expected in reported.items():
            with self.subTest(active=active):
                state = {"active": active, "config_sha256": config_digest(config)}
                (base / "state.json").write_text(json.dumps(state), encoding="utf-8")
                paths = {item["path"] for item in leftovers(self.root)}
                self.assertEqual(paths & {*reported[True], *reported[False]}, expected)
        with self.subTest("config changed after init"):
            (base / "state.json").write_text(json.dumps({"active": True}), encoding="utf-8")
            self.assertEqual(leftovers(self.root), [])

    def test_progress_keeps_the_newest_handoff_and_archives_the_rest_once(self) -> None:
        progress = self.runtime / "progress.md"
        archive = self.runtime / "archive" / "progress-2026-11.md"
        now = datetime(2026, 11, 4)
        real_write = records._atomic_write

        def fail_on_progress(path: Path, text: str) -> None:
            if path.name == progress.name:
                raise PermissionError(13, "locked")
            real_write(path, text)

        with mock.patch("harness.records._atomic_write", side_effect=fail_on_progress):
            moved, error = archive_progress(self.root, now)
        self.assertEqual((moved, progress.read_text(encoding="utf-8")), (0, PROGRESS))
        self.assertIn("cannot archive progress.md", error or "")

        self.assertEqual(archive_progress(self.root, now), (2, None))
        self.assertEqual(
            progress.read_text(encoding="utf-8"),
            "# Progress\n\n## 11-04 newest\n`keep_t3.py` is still in use.\n",
        )
        archived = archive.read_text(encoding="utf-8")
        self.assertEqual(archived.count("## 11-03 older"), 1)
        self.assertIn("## not a heading\n```\n`verify_t3.py` passed.\n\n## 11-02 oldest\ndone\n", archived)
        self.assertEqual(archive_progress(self.root, now), (0, None))


if __name__ == "__main__":
    unittest.main()
