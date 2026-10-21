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
   交给被测方的题目、数据、样本或请求，连同决定它们的 schema / 模板 / 候选定义，在实现前写进设计并附
   渲染样例；改它们等于改设计。删除或放宽一道门时，写明它防的风险由哪道检查接替。
3. 只把最近 1–2 项写进 `task.md`，状态为 `📝 proposed`，`rev` 绑定 plan 的 `rN`。
4. 配置 reviewer 时，提交后运行 `plan-review`：每个 task 只在第一次出现时审一次，设计之后再改也不重审。
   reviewer 只给准入意见，分 `must`（不改就方向错、结论错或白跑昂贵实验）与 `suggest`（严谨性），各最多 3 条。
5. 逐条回应 `must`：照改后 `plan-review --respond <task> --item N=applied`；只在与事实不符时
   `--item N=reject --reason "<事实>"`，只驳一次。`suggest` 酌情改或跳过，不必回应。不回审。
   再用平台的结构化提问能力给 human：`approve / revise / continue automatically`，附上逐 task 意见与回应。
   带 `human: true` 的 must 由 human 选，用 human 原话 `plan-review --approve <task> --reason` 记下；
   human 要求重审用 `--again`。reviewer 报告缺失或失败、human 未批准时，不实验、不改实现。
6. 批准后 `Plan Review: approved`，最高优先级行转 doing，其余转 todo；无人值守自批准写
   `Plan Review: unreviewed`，但配置 reviewer 时仍须完成独立 plan review。
7. 项目有多个 Goal 时，第一个 Goal 的 Gate 同时对齐 `task.md` 的主线一节（格式见 `task-state`），
   human 批准后写 `Mainline Review: approved`。

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
4. 独立 plan review 与 human review 后恢复唯一 doing，再 `resume`；task reviewer 选了 `ask_human` / `stop`
   而 human 决定开新 task 时，human 把它批为 `🔬 doing` 后直接 `init`，不用 `disable`。

对话里的「明白」不算 RECONCILE；四步落盘后才继续。

## CLOSE

**CLOSE 不只是追加摘要，还要让已闭合记录退出活跃工作集。**

CLOSE 分两段：

1. **locked verifier 前**：worker 按 `experiment-design` 的 CLOSE self-audit 回读本 task 完整 diff，
   精炼文档并处理临时脚本。
2. **verifier 通过后**：收口结论、归档已闭合记录；配置 reviewer 时下一步决策仍归 reviewer。

verifier 通过后：

1. 把该 task 的多轮实验合并成一个 task 结论，更新「当前结论」与下一步决策；
2. active Experiment Log 只保留未闭合决策；已收口行改为 `promoted / superseded / archived`，
   移到 linked archive，活跃表只留一个 task 级指针；
3. 通知 `task-state` 归档 closed task 与旧交接快照，通知 `agent-memory` 只保留未来仍会改变选择的
   结论、`disproved / rejected` 与证据指针；
4. reviewer 决定落盘后（未配置 reviewer 时 verifier 通过后）删除该 task 的 run 目录；
   位置与逐 run 表的要求归 `experiment-design`。

### 主线交接

- reviewer 对主线 Goal 选 `stop` 时，把它在主线表的行改 `✅ done`、下一行改 `▶ next`，为 `▶ next` 的 Goal
  写 plan、跑独立 plan review 再开工，不停在 DONE；`Mainline Review` 不是 `approved` 时交 human。
- 增删 Goal 或改顺序是 `replan`：`Mainline Review` 改 `proposed`，交 human。
- 由故障或基础设施问题引出的 Goal 是支线：不进主线表，plan 头部写 `Side of: <主线 Goal>` 与预算，
  开支线要 human 批准。

Goal 完成或 pivot 时冻结 plan document 为 as-built；活跃头部只留最终 Goal、当前结论、边界与
archive index。sub-exp 不删，但不再默认加载。删除只被本 Goal 文档引用的一次性脚本，判据归
`experiment-design`；暂停中的 Goal 的脚本等它关闭再处理。具体格式分别归
`experiment-design`、`task-state`、`agent-memory`，本 skill 只拥有 task / Goal 的退役时机。

active Experiment Log 超过 10 行是漏执行告警，不是按行截断规则。

项目配置了 reviewer 时，「更新下一步决策」归 reviewer：锁定 verifier 通过后 Harness 自动运行
`harness review`，worker 只做事实核对；prompt 与决策格式见 `harness/prompts/task_review.md`。
标 done、把关闭 task 的标题段移到 plan 同目录的 `<plan>-archive.md`、改写指向它们的链接由 Harness 在
reviewer 决定落盘后完成，reviewer 与 worker 都不手工搬。
