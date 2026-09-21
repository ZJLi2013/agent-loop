from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def text(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


class PlanningContractTest(unittest.TestCase):
    def test_review_gate_is_a_real_task_state(self) -> None:
        rule = text("rules/agent-loop.mdc")
        planning = text(".cursor/skills/feature-planning/SKILL.md")
        task_state = text(".cursor/skills/task-state/SKILL.md")

        for content in (rule, planning, task_state):
            self.assertIn("📝 proposed", content)
        self.assertIn("Human Review Gate", planning)
        self.assertIn("批准前不进实验、不改实现", planning)
        self.assertIn("若干 `📝 proposed` + 零行 doing", task_state)

    def test_feature_goal_is_required_before_experiment(self) -> None:
        rule = text("rules/agent-loop.mdc")
        planning = text(".cursor/skills/feature-planning/SKILL.md")
        experiment = text(".cursor/skills/experiment-design/SKILL.md")

        self.assertIn("feature 开发进入 `experiment-design` 前", rule)
        self.assertIn("先写 feature 文档的 Goal / 边界", planning)
        self.assertIn("## 准入：feature 先于 exp", experiment)
        self.assertIn("standalone diagnostic", experiment)

    def test_plan_is_incremental_and_reconciles_human_corrections(self) -> None:
        rule = text("rules/agent-loop.mdc")
        planning = text(".cursor/skills/feature-planning/SKILL.md")
        task_state = text(".cursor/skills/task-state/SKILL.md")

        self.assertIn("一个未验证假设", planning)
        self.assertIn("一个未验证假设", task_state)
        self.assertIn("最近 1–2 个", planning)
        for content in (rule, planning, task_state):
            self.assertIn("RECONCILE", content)
        self.assertLess(
            rule.index("更新 feature 文档的 Goal"),
            rule.index("重排 `task.md`"),
        )


if __name__ == "__main__":
    unittest.main()

