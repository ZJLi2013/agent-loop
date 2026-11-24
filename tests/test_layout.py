from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from harness.core import initialize
from harness.errors import HarnessError
from harness.lint import lint_changed
from harness.records import close_task, design_location_error, leftovers, mainline_handoff, open_task_ids

PLAN_HEAD = ("# {name}\n\nPlan Revision: 1\nPlan Review: approved\n\n- 目标：a\n- 现状：a\n- 下一步：a\n\n"
             "## Goal\n\n{name}\n\n")
EXP_HEAD = "# a 的实验细节\n\n"


class LayoutTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.write("verify.py", "print('OK')\n")
        self.write("features/a.md", PLAN_HEAD.format(name="a") + "## a1 设计\n\n- rev：r1\n")
        self.write("features/b.md", PLAN_HEAD.format(name="b") + "## b1 设计\n\n- rev：r1\n")
        self.tasks(("a1", "../features/a.md#a1-设计"), ("b1", "../features/b.md#b1-设计"))
        self.git("init", "-q")
        self.commit()

    def tearDown(self) -> None:
        self.temp.cleanup()

    def write(self, name: str, text: str) -> None:
        path = self.root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def read(self, name: str) -> str:
        return (self.root / name).read_text(encoding="utf-8")

    def git(self, *args: str) -> str:
        return subprocess.run(
            ["git", "-c", "user.name=t", "-c", "user.email=t@t", *args],
            cwd=self.root, check=True, capture_output=True, text=True,
        ).stdout

    def commit(self) -> None:
        self.git("add", "-A")
        self.git("commit", "-qm", "x")

    def tasks(self, *rows: tuple[str, str], mainline: str = "") -> None:
        body = "".join(f"| {task} | [设计]({link}) | 过 → done | 🔬 doing |\n" for task, link in rows)
        self.write(".agent-loop/task.md", f"# Tasks\n{mainline}\n## Goal\n\n| id | task | 验收检查点 | 状态 |\n|---|---|---|---|\n{body}")

    def init(self, task: str, plan_doc: str) -> None:
        initialize(self.root, task_id=task, plan_doc=plan_doc, verifier_argv=[sys.executable, "verify.py"])

    def configure(self, plan_doc: str) -> None:
        self.write(".harness/config.json", json.dumps(
            {"plan_doc": plan_doc, "lint": {"base": self.git("rev-parse", "HEAD").strip()}}))

    def test_two_features_in_one_directory_keep_their_own_tasks(self) -> None:
        self.assertEqual(open_task_ids(self.root, plan_doc="features/a.md"), ["a1"])

        self.tasks(("b1", "../features/b.md#b1-设计"), mainline=(
            "\n## 主线\n\nMainline Review: approved\n\n| Goal | 问题 | 退出条件 | 状态 | plan |\n|---|---|---|---|---|\n"
            "| a | a | a | ✅ done | [plan](../features/a.md) |\n| b | b | b | ▶ next | [plan](../features/b.md) |\n"))
        self.write(".agent-loop/archive/tasks.md", "| P | id | rev | task | 验收检查点 | 状态 | 失败 |\n"
                   "|---|---|---|---|---|---|---|\n| — | a1 | r1 | a | done | ✅ done | 0 |\n")
        self.write("features/b-notes.md", "notes\n")
        self.assertEqual(leftovers(self.root), [])

        close_task(self.root, "features/a.md", "a1")
        self.assertIn("## b1 设计", self.read("features/b.md"))

    def test_next_goal_with_two_features_hands_off_to_either(self) -> None:
        self.write("features/c.md", PLAN_HEAD.format(name="c"))
        self.tasks(mainline=(
            "\n## 主线\n\nMainline Review: approved\n\n| Goal | 问题 | 退出条件 | 状态 | plan |\n|---|---|---|---|---|\n"
            "| a | a | a | ✅ done | [plan](../features/a.md) |\n"
            "| b | b | b | ▶ next | [b](../features/b.md)、[c](../features/c.md) |\n"))

        self.assertTrue(mainline_handoff(self.root, "features/a.md", "features/c.md"))
        self.assertFalse(mainline_handoff(self.root, "features/b.md", "features/c.md"))

    def test_new_goal_in_old_location_is_refused_even_after_review(self) -> None:
        self.write(".agent-loop/plans/g/plan.md", PLAN_HEAD.format(name="g") + "## g1 设计\n\n- rev：r1\n")
        self.tasks(("g1", "plans/g/plan.md#g1-设计"))

        with self.assertRaisesRegex(HarnessError, "must be features/<feature>.md"):
            self.init("g1", ".agent-loop/plans/g/plan.md")

    def test_old_plan_with_an_archived_task_is_accepted(self) -> None:
        self.write(".agent-loop/plans/g/plan.md", PLAN_HEAD.format(name="g")
                   + "## g1 设计\n\n- rev：r1\n\n## Experiment Log\n\n| g0 | run | pass |\n")
        self.write(".agent-loop/archive/tasks.md", "| P | id | rev | task | 验收检查点 | 状态 | 失败 |\n"
                   "|---|---|---|---|---|---|---|\n| — | g0 | r1 | g | done | ✅ done | 0 |\n")
        self.tasks(("g1", "plans/g/plan.md#g1-设计"))

        self.init("g1", ".agent-loop/plans/g/plan.md")

    def test_design_link_to_an_exp_or_another_feature_is_refused(self) -> None:
        self.write("exps/a.md", EXP_HEAD + "## a1 设计\n")
        self.write("features/b.md", self.read("features/b.md") + "\n## a1 设计\n")
        self.write("features/sub-exp/a1.md", "design\n")
        cases = (
            ("own task section", "../features/a.md#a1-设计", True),
            ("exp document", "../exps/a.md#a1-设计", False),
            ("another feature", "../features/b.md#a1-设计", False),
            ("sub-exp beside the feature", "../features/sub-exp/a1.md", False),
        )
        for name, link, located in cases:
            with self.subTest(name):
                self.tasks(("a1", link))
                error = design_location_error(self.root, "a1", "features/a.md")
                self.assertEqual(error is None, located, error)

    def test_close_unlinks_the_section_in_features_and_exps(self) -> None:
        self.write("exps/a.md", EXP_HEAD + "## 读数\n\n做法见 [a1 设计](../features/a.md#a1-设计)。\n")
        self.write("features/b.md", self.read("features/b.md") + "\n沿用 [a1 设计](a.md#a1-设计)。\n")

        close_task(self.root, "features/a.md", "a1")
        once = {name: self.read(name) for name in ("exps/a.md", "features/b.md", "features/a.md")}
        close_task(self.root, "features/a.md", "a1")

        self.assertIn("做法见 a1 设计。", once["exps/a.md"])
        self.assertIn("沿用 a1 设计。", once["features/b.md"])
        self.assertNotIn("## a1 设计", once["features/a.md"])
        self.assertEqual({name: self.read(name) for name in once}, once)

    def test_lint_exempts_only_the_current_feature_sections_and_the_exp_log(self) -> None:
        self.configure("features/a.md")
        self.write("features/a.md", self.read("features/a.md") + "做法待 human 定\n")
        self.write("features/b.md", self.read("features/b.md") + "\n## 下一步\n\n做法待 human 选\n")
        self.write("exps/a.md", EXP_HEAD + "## 结果\n\n| a1 | 读数 |\n\n## Experiment Log\n\n| a1 | run | pass |\n")
        self.git("add", "-A")

        hits = [p.split(": ")[0] for p in lint_changed(self.root) if "design-state" in p]

        self.assertEqual(sorted(hits), ["exps/a.md:5", "features/b.md:20"])

    def test_feature_needs_first_screen_and_no_experiment_log(self) -> None:
        self.write("features/c.md", "# c\n\nPlan Revision: 1\n\n## Goal\n")
        self.write("features/d.md", PLAN_HEAD.format(name="d") + "## Experiment Log\n")
        self.write("features/e.md", PLAN_HEAD.format(name="e") + "exp 的样子：\n```markdown\n## Experiment Log\n```\n")
        self.git("add", "-A")

        problems = lint_changed(self.root)

        self.assertIn("features/c.md: entry fields missing before the first ## section: 目标、现状、下一步", problems)
        self.assertIn("features/d.md:14: Experiment Log belongs in exps/d.md", problems)
        self.assertEqual([p for p in problems if p.startswith("features/e.md")], [])

    def test_exp_holds_only_details_and_data(self) -> None:
        self.write("exps/z.md", "# z\n\n## 读数\n")
        self.write("exps/line/01-q.md", "# q\n")
        self.write("exps/a.md", EXP_HEAD + "## 当前结论\n- **现状**：x\n- rev：r1\n")
        self.write("exps/b.md", EXP_HEAD + "## 三档读数\n配置：seed 0\n```markdown\n## 当前结论\n```\n"
                   "| 档 | p95 |\n|---|---|\n| 0 | 2.4 |\n\n## Experiment Log\n\n| b1 | run | pass |\n")
        self.git("add", "-A")

        problems = lint_changed(self.root)

        self.assertIn("exps/z.md: no features/z.md; each exp document has a feature of the same path", problems)
        self.assertIn("exps/line/01-q.md: no features/line/01-q.md; each exp document has a feature of the same path",
                      problems)
        self.assertEqual(sorted(p.split(": ")[0] for p in problems if p.startswith("exps/a.md")),
                         ["exps/a.md:3", "exps/a.md:4", "exps/a.md:5"])
        self.assertEqual([p for p in problems if p.startswith("exps/b.md")], [])

    def test_nested_features_and_exps_mirror_each_other(self) -> None:
        self.write("features/g/x.md", PLAN_HEAD.format(name="x") + "## x1 设计\n\n- rev：r1\n")
        self.write("exps/g/x.md", EXP_HEAD + "## 读数\n\n做法见 [x1 设计](../../features/g/x.md#x1-设计)。\n")
        self.write("features/g/y.md", "# y\n\nPlan Revision: 1\n\n## Goal\n")
        self.write("features/g/readme.md", "# g\n\n- 目标：a\n- 现状：a\n- 下一步：a\n\n## 实验\n\n- x 测得 3 项 [x](x.md)\n")
        self.write("exps/g/readme.md", "# g\n\n| 实验 | 数据 |\n|---|---|\n| x | [x](x.md) |\n")
        self.write("exps/g/z.md", EXP_HEAD)
        self.git("add", "-A")

        problems = [p for p in lint_changed(self.root) if p.startswith(("features/g/", "exps/g/"))]
        self.assertEqual(sorted(problems), [
            "exps/g/z.md: no features/g/z.md; each exp document has a feature of the same path",
            "features/g/y.md: entry fields missing before the first ## section: 目标、现状、下一步",
        ])

        self.tasks(("x1", "../features/g/x.md#x1-设计"))
        self.assertIsNone(design_location_error(self.root, "x1", "features/g/x.md"))
        self.write("features/g/readme.md", self.read("features/g/readme.md") + "\n## r1 设计\n")
        self.tasks(("r1", "../features/g/readme.md#r1-设计"))
        self.assertIn("must be features/<feature>.md", design_location_error(self.root, "r1", "features/g/readme.md"))

        close_task(self.root, "features/g/x.md", "x1")
        self.assertIn("做法见 x1 设计。", self.read("exps/g/x.md"))

    def test_a_group_directory_holds_its_own_pair(self) -> None:
        self.write("lab/features/x.md", PLAN_HEAD.format(name="x") + "## x1 设计\n\n- rev：r1\n")
        self.write("lab/exps/x.md", EXP_HEAD + "## 读数\n\n做法见 [x1 设计](../features/x.md#x1-设计)。\n"
                   "\n## Experiment Log\n\n| x1 | run | pass |\n")
        self.write("lab/features/y.md", PLAN_HEAD.format(name="y") + "## Experiment Log\n")
        self.write("lab/exps/z.md", EXP_HEAD)
        self.write("other/features/w.md", PLAN_HEAD.format(name="w") + "沿用 [x1 设计](../../lab/features/x.md#x1-设计)。\n")
        self.write("plans/g/exps/run.md", "# run\n\n## 当前结论\n")
        self.tasks(("x1", "../lab/features/x.md#x1-设计"))
        self.configure("lab/features/x.md")
        self.git("add", "-A")

        problems = [p for p in lint_changed(self.root) if p.startswith(("lab/", "plans/"))]
        self.assertEqual(sorted(problems), [
            "lab/exps/z.md: no lab/features/z.md; each exp document has a feature of the same path",
            "lab/features/y.md:14: Experiment Log belongs in lab/exps/y.md",
        ])

        self.assertIsNone(design_location_error(self.root, "x1", "lab/features/x.md"))
        close_task(self.root, "lab/features/x.md", "x1")
        self.assertIn("做法见 x1 设计。", self.read("lab/exps/x.md"))
        self.assertIn("沿用 x1 设计。", self.read("other/features/w.md"))

    def test_a_done_goal_does_not_claim_its_feature_subdirectory(self) -> None:
        self.write("features/g/x.md", PLAN_HEAD.format(name="x"))
        self.commit()
        self.tasks(mainline=(
            "\n## 主线\n\nMainline Review: approved\n\n| Goal | 问题 | 退出条件 | 状态 | plan |\n|---|---|---|---|---|\n"
            "| g | g | g | ✅ done | [plan](../features/g/x.md) |\n"))
        self.write("features/g/notes.md", "notes\n")

        self.assertEqual(leftovers(self.root), [])

    def test_untracked_feature_is_refused(self) -> None:
        self.write(".gitignore", "features/c.md\n")
        self.commit()
        self.write("features/c.md", PLAN_HEAD.format(name="c"))

        self.assertIn("features/c.md: ignored by git; features/ and exps/ are tracked", lint_changed(self.root))


if __name__ == "__main__":
    unittest.main()
