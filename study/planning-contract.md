# 渐进计划与人工纠偏

Plan Revision: 2
Plan Review: approved

## Goal

让一份 plan document 先承载 human 的真实意图，再用可验证的小步 task 推进；human 纠偏后，旧计划及
正在运行的命令都不能越过 review gate 继续驱动 loop。

## 结论

三道机械门已落地：新计划先进入 `📝 proposed`；一个 task 最多跨越一个未验证假设；
human 纠偏必须先更新 plan Goal，再原子地重排 `task.md`。`experiment-design` 只在 plan Goal
存在且 task 获批后进入；一次性 diagnostic 的 plan 可以就是实验记录。Plan Revision 与运行时
pause gate 已落地：pause 可中断 runner，plan review、task `rN` 与 runtime revision 一致后
才能 resume。Goal、当前结论、下一步决策与 Experiment Log 统一在 plan document；action /
elapsed / failure / stale / preCompact 触发 Goal Review，详细实验按需拆 linked sub-exp。

## Pipeline

```text
Goal
  ↓
plan document（Goal / 当前结论 / 下一步决策 / Experiment Log）
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
Harness pause（必要时中断 runner）
  ↓
更新 plan Goal + Plan Revision ─► 标记旧 task 去向
  └──────────────────────────────► 重排 task.md ─► approve ─► resume
```

## Contract

- 工作不得从 `task.md` 直接跳到实验；缺少 plan Goal 时先回 `work-planning`。
- `experiment-design` 只拥有实验假设、方案、预期、判据与 evidence，不代写 plan 的稳定头部。
- 详细实验需要拆分时只建 linked sub-exp；不另造 feature / exp 两套文档。
- task 同时依赖两个未验证假设，或失败后无法判断是哪条假设错了，就必须拆小。
- 远期 task 只留候选，不提前写死实现；最近 1–2 项才写可执行检查点。
- user 新消息纠正 Goal、scope 或优先级时，立即中断旧计划并完成 RECONCILE，不能只在对话里确认。
- plan document 固定写 `Plan Revision: N` 与 `Plan Review: proposed|approved|unreviewed`。
- Harness 初始化 task 时锁定 plan revision；pause 后拒绝新命令。修改意见要求 revision 递增，
  且 review 变为 approved / unreviewed 后才允许 resume。

## Verification

proposed / 渐进拆解 / RECONCILE 是 `work-planning` 的 Policy，由 human review；不再用
`assertIn()` 匹配说明文案。可执行 guard 由以下测试固定：

- `tests.test_protocol`：pause / resume / verify / stop 的合法转移；
- `tests.test_harness_pause`：proposed 自动暂停、运行中 pause、旧 revision、未批准 review、
  task `rN` 不一致时拒绝执行或 resume。

