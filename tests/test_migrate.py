from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from harness import failures, migrate
from harness.core import initialize
from harness.errors import HarnessError
from harness.migrate import migrate_tasks
from harness.plan import task_plan_revision

PLAN = "# Plan\n\nPlan Revision: 3\nPlan Review: approved\n\n## Tasks\n\n" + "".join(
    f"## {task_id} design\n\n{task_id} body\n\n" for task_id in ("a", "b", "c", "d", "e")
)
LEGACY = """# Tasks

## Goal（g）

| P | id | rev | task | 验收检查点 | 状态 | 失败 |
|---|---|---|---|---|---|---|
| P2 | b | r3 | B 能否…？[设计](plans/g/plan.md#b-design) | 过 → P1；不过 → 回 plan | 🚧 blocked a | 0 |
| P1 | a | r3 | A 能否…？[设计](plans/g/plan.md#a-design) | 过 → P2；不过 → 回 plan | 🔬 doing | 2 |
| P1 | c | r3 | C 能否…？[设计](plans/g/plan.md#c-design) | 过 → P2 | ⬜ todo | 0 |

## Candidates

| P | 候选 | 进入条件 |
|---|---|---|
| 1 | 下一步 | P2 完成 |
"""
FIXED = LEGACY.replace("过 → P1；", "过 → a；")
MIGRATED_TABLE = """| id | task | 验收检查点 | 状态 |
|---|---|---|---|
| a | A 能否…？[设计](plans/g/plan.md#a-design) | 过 → b；不过 → 回 plan | 🔬 doing |
| c | C 能否…？[设计](plans/g/plan.md#c-design) | 过 → b | ⬜ todo |
| b | B 能否…？[设计](plans/g/plan.md#b-design) | 过 → a；不过 → 回 plan | 🚧 blocked a |
"""
SECOND_GOAL = """
## Goal（h）

| P | id | rev | task | 验收检查点 | 状态 | 失败 |
|---|---|---|---|---|---|---|
| P5 | e | r3 | E？[设计](plans/g/plan.md#e-design) | 过 → P1 | ⬜ todo | 0 |
| P1 | d | r3 | D？[设计](plans/g/plan.md#d-design) | 过 → P5 | ⬜ todo | 1 |
"""


class MigrateTasksTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.task = self.root / ".agent-loop" / "task.md"
        self.plan = self.root / ".agent-loop" / "plans" / "g" / "plan.md"
        self.plan.parent.mkdir(parents=True)
        self.plan.write_text(PLAN, encoding="utf-8")

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, text: str) -> None:
        self.task.write_text(text, encoding="utf-8")

    def read(self, path: Path) -> str:
        return path.read_text(encoding="utf-8")

    def test_ambiguous_reference_stops_migration_before_any_write(self) -> None:
        self.write(LEGACY)

        with self.assertRaisesRegex(HarnessError, r"(?s)wrote nothing.*`P1` matches 2 rows \(a, c\)"):
            migrate_tasks(self.root)

        self.assertEqual(self.read(self.task), LEGACY)
        self.assertEqual(self.read(self.plan), PLAN)
        self.assertFalse((self.root / ".harness" / "migrate").exists())

    def test_migration_produces_the_design_example(self) -> None:
        self.write(FIXED)

        migrate_tasks(self.root)

        text = self.read(self.task)
        self.assertIn(MIGRATED_TABLE, text)
        self.assertIn("| 1 | 下一步 | b 完成 |", text)
        self.assertEqual(self.read(self.plan).count("- rev：r3"), 3)
        self.assertIn("## a design\n\n- rev：r3\n\na body\n", self.read(self.plan))
        self.assertEqual([task_plan_revision(self.root, task_id) for task_id in "abc"], [3, 3, 3])

    def test_migrated_nonzero_count_is_kept(self) -> None:
        self.write(FIXED)

        migrate_tasks(self.root)

        self.assertEqual([failures.count(self.root, task_id) for task_id in "abc"], [2, 0, 0])

    def test_each_goal_table_sorts_on_its_own(self) -> None:
        self.write(FIXED + SECOND_GOAL)

        migrate_tasks(self.root)

        text = self.read(self.task)
        self.assertIn(MIGRATED_TABLE, text)
        self.assertIn("| d | D？[设计](plans/g/plan.md#d-design) | 过 → e | ⬜ todo |\n"
                      "| e | E？[设计](plans/g/plan.md#e-design) | 过 → d | ⬜ todo |", text)
        self.assertLess(text.index("## Goal（g）"), text.index("## Goal（h）"))
        self.assertEqual(failures.count(self.root, "d"), 1)

    def test_interrupted_migration_restores_and_completes(self) -> None:
        self.write(FIXED)

        with mock.patch.object(migrate.failures, "import_counts", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                migrate_tasks(self.root)
        self.assertIn(MIGRATED_TABLE, self.read(self.task))

        result = migrate_tasks(self.root)

        self.assertTrue(result["migrated"])
        self.assertIn(MIGRATED_TABLE, self.read(self.task))
        self.assertEqual(self.read(self.plan).count("- rev：r3"), 3)
        self.assertEqual(failures.count(self.root, "a"), 2)
        self.assertFalse(migrate_tasks(self.root)["migrated"])

    def test_rerun_does_not_import_failures_twice(self) -> None:
        self.write(FIXED)
        real = migrate.atomic_write_json

        def fail_when_done(path: Path, value: dict[str, object]) -> None:
            if value.get("done"):
                raise OSError("interrupted")
            real(path, value)

        with mock.patch.object(migrate, "atomic_write_json", side_effect=fail_when_done):
            with self.assertRaises(OSError):
                migrate_tasks(self.root)
        failures.add(self.root, "a", "tried once more")

        migrate_tasks(self.root)

        self.assertEqual(failures.count(self.root, "a"), 3)
        self.assertIn(MIGRATED_TABLE, self.read(self.task))

    def test_init_refuses_the_seven_column_table(self) -> None:
        self.write(FIXED)

        with self.assertRaisesRegex(HarnessError, "migrate-tasks"):
            initialize(
                self.root, task_id="a", plan_doc=".agent-loop/plans/g/plan.md",
                verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
            )
        self.assertFalse((self.root / ".harness" / "state.json").exists())

    def test_init_without_reviewer_reads_four_columns(self) -> None:
        self.write(FIXED)
        migrate_tasks(self.root)

        _, state = initialize(
            self.root, task_id="a", plan_doc=".agent-loop/plans/g/plan.md",
            verifier_argv=[sys.executable, "-S", "-c", "print('OK')"],
        )

        self.assertEqual((state["phase"], state["plan_revision"]), ("ready", 3))


if __name__ == "__main__":
    unittest.main()
