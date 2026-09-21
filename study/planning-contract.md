# 渐进计划与人工纠偏

## Goal

让 feature 设计先承载 human 的真实意图，再用可验证的小步 task 推进；human 纠偏后，旧计划不能继续驱动 loop。

## 结论

三道机械门已落地：新计划先进入 `📝 proposed`；一个 task 最多跨越一个未验证假设；
human 纠偏必须先更新 feature Goal，再原子地重排 `task.md`。`experiment-design` 只在 feature Goal
存在且 task 获批后进入，standalone diagnostic 是唯一 exp-only 例外。

## Pipeline

```text
Goal
  ↓
feature.md（Goal / 边界 / 渐进设计）
  ↓
task.md：📝 proposed
  ↓
Human Review Gate ── approve / revise / unattended 自批准
  ↓
只展开最近 1–2 个 task
  ↓
一项通过 ─► 用新 evidence 重排剩余项

human correction
  ↓
暂停当前动作 ─► 更新 feature Goal ─► 标记旧 task 去向
  └──────────────────────────────► 重排 task.md ─► 新的唯一 🔬 doing
```

## Contract

- feature 开发不得从 `task.md` 直接跳到 exp；缺少 feature Goal 时先回 `feature-planning`。
- `experiment-design` 只拥有实验假设、方案、预期、判据与记录，不代写 feature 系统设计。
- 一次性 diagnostic 可以只写 exp，但必须在 task 中明确标为 diagnostic。
- task 同时依赖两个未验证假设，或失败后无法判断是哪条假设错了，就必须拆小。
- 远期 task 只留候选，不提前写死实现；最近 1–2 项才写可执行检查点。
- user 新消息纠正 Goal、scope 或优先级时，立即中断旧计划并完成 RECONCILE，不能只在对话里确认。

## Tests

`python -m unittest tests.test_planning_contract -v` 固定以下契约：

- `agent-loop`、`feature-planning`、`task-state` 同时认识 `📝 proposed`；
- feature Goal 是 `experiment-design` 的前置条件；
- planning 与 task-state 都限制一个未验证假设、最近 1–2 个 task；
- RECONCILE 的顺序是先更新 feature Goal，再重排 `task.md`。

