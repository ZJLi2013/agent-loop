---
name: work-planning
description: >-
  把 Goal 落成一份 plan document、最近 1–2 个渐进 task 与 Human Review Gate；
  处理 Plan Revision、Goal Review 和人工纠偏后的 RECONCILE。
  Use for new goals, proposed plans, plan review, goal refresh, or user corrections.
---

# Work Planning

本 skill 是 planning Policy。状态转移归 `harness/protocol.py`，task schema 归 `task-state`，
实验假设与判据归 `experiment-design`。

## 一份 plan document

默认只建一份文档，不区分 feature / exp：

```markdown
# <Goal 名称>

Plan Revision: 1
Plan Review: proposed

## Goal
<一句话：human 要解决什么问题>

## 当前结论
<现在为真的判断；设计中就明确写未验证>

## 下一步决策
<最近动作及为什么>

## 系统 / Pipeline
（确实存在系统路径时才写）

## Experiment Log
<单次实验的假设、判据、结果与证据>
```

单个实验直接追加到 Experiment Log。只有同一 Goal 下出现多个独立实验、详细日志遮蔽稳定头部、
或需要并行维护时，才拆 linked `sub-exp/<id>.md`；结论与链接始终回填 plan document。

## PLAN → REVIEW → READY

1. 先写 Goal / 边界，再从它拆 task；不能先列实现步骤再反推 Goal。
2. 一个 task 最多跨一个未验证假设；失败后无法定位哪条假设错了，就先拆 probe / inspection。
3. 只把最近 1–2 项写进 `task.md`，状态为 `📝 proposed`，`rev` 绑定 plan 的 `rN`。
4. 正常模式用平台的结构化提问能力给 human：
   `approve / revise / continue automatically`。批准前不实验、不改实现。
5. 批准后 `Plan Review: approved`，最高优先级行转 doing，其余转 todo；无人值守自批准写
   `Plan Review: unreviewed`。

远期路线只作为 plan 中的候选。每项拿到 evidence 后再生成下一项，不一次写死整条路线。

## Goal Review

Harness 因 action count、elapsed time、长命令结束、失败、evidence stale 或 context compact
触发 `goal_review_due` 时，先回答并落盘：

1. 当前 Goal 是什么；
2. 新 evidence 改变了什么；
3. 下一动作为什么推进 Goal；
4. `continue / replan / stop`。

- `continue`：更新 plan 的当前结论 / 下一步决策，调用 `goal-review --decision continue`；
- `replan`：调用 `goal-review --decision replan`，`Plan Revision` +1、review 改 proposed，
  再走 Human Review Gate；
- `stop`：记录边界，调用 `goal-review --decision stop`。

## Human correction

只问进展时读 task、journal 与 evidence 回答，不自动改 revision。形成 Goal / scope / 优先级修改后：

1. `pause --require-revision --reason "<纠偏>"`；
2. 更新 plan Goal / 边界，revision +1、review 改 proposed；
3. 旧 task 逐项保留、blocked 或 dropped；新 task 绑定新 `rN`；
4. human review 后恢复唯一 doing，再 `resume`。

对话里的「明白」不算 RECONCILE；四步落盘后才继续。

## CLOSE

task 通过后把 Experiment Log 的关键 evidence 提炼到「当前结论」，更新下一步决策；
细节留在 log / sub-exp。全部完成时 plan document 是 as-built，不需要再复制一份总结。
