# Study：按 feature 组织的调研与设计依据

agent-loop 是服务于其他研究与工程项目的 harness。这里的调研大多产生于某个 feature 的实现过程，
所以按 feature 分目录：每个目录回答该 feature 为什么这样做、参照了谁、放弃了什么。
当前架构以 [`design.md`](../../design.md) 为准，执行方法见 [`skills/README.md`](../../skills/README.md)，
真实运行中发现的问题见 [issues](https://github.com/ZJLi2013/agent-loop/issues)。

## Feature 目录

| Feature | 状态 | 文档 | 当前 owner |
|---|---|---|---|
| [`harness/`](harness/) 执行、预算与完成门 | 已落地 | [最小 Harness](harness/harness.md)；[心跳](harness/heartbeat.md)：进程存活与有效进展的区分 | `harness/`、`skills/agent-heartbeat` |
| [`planning-review/`](planning-review/) 规划、纠偏与评审 | 已落地 | [渐进计划](planning-review/planning-contract.md)；[worker / reviewer](planning-review/multi_agent.md)：角色分工与外部参照 | `skills/work-planning`、`harness/plan*.py`、`harness/review.py` |
| [`memory/`](memory/) 记忆与记录收敛 | 已落地 | [Memory](memory/memory.md)：检索与写回；[记录生命周期](memory/experiment-record-lifecycle.md)：归档与证据指针 | `skills/agent-memory`、`skills/task-state`、`harness/records.py` |
| [`exploration-mode/`](exploration-mode/) 开放研究问题（v0.2） | 提案 | [探索模式](exploration-mode/exploration-mode.md)；[决定表](exploration-mode/research-automation.md)：外部系统对照；[研究地图模板](exploration-mode/research-map-template.md)：初稿；[autoresearch](exploration-mode/autoresearch.md)：单指标循环的控制结构 | 尚无；见 [ROADMAP](../../ROADMAP.md) |

## 跨 feature 文档

- [设计沿革](agent_loop.md)：为什么需要这个循环，哪些责任逐步移到了 Harness。
- [业界实践与能力边界](industry-practices.md)：独立 radar、项目验证与 RSI 的范围判断。
- [Research / RSI 工作追踪](research-rsi-track.md)：持续更新的 research agent 与自改进工作清单，及每项对本库的影响。
- [skill 依赖解析](skill-dependency-resolution.md)：安装器跨来源解析 `requires` 时取 graphlib、不取 pip resolver 的理由。
- [设计文档的内容分流](design-document-routing.md)：planning 与 plan reviewer 怎样把内容分到设计文档、CHANGELOG 与 plan，业界做法，以及两处分流规则为何都撤回。
- [范围判据回放](scope-replay.md)：只读范围一节的 reviewer 对六条历史输入判对五条，#77 暴露的处置表缺口。
- [改假设时换一层](layer-shift-replay.md)：同一组件内第二个假设被推翻时上移到组件 / 方法类别对照，两个阶段不动 Goal 时交 human；改动前后的回放，以及三处改动前已成立而不加的措辞。
- [先用上再加深](use-first-replay.md)：供读者反复取用的产出，第一个退出条件是一次真实使用，用上之前不加深；改动前后的回放，以及触发条件为什么不写「给人读」。
- [按需 skill 与通用 rule 的迁出清单](skill-migration.md)：七个 skill 与两条 rule 为什么迁到私有 pack、各自的依赖，以及核心里删掉的点名。

初次阅读：设计沿革 → 业界实践 → 按 feature 进入。需要修改当前实现时，先读 `design.md` 与对应 owner，
再查这里的依据。社区项目的用途对照见 [Related projects](../related-projects.md)，面向选择工具的读者。

## 文档边界

- **当前设计**说明系统现在如何工作，归 `design.md` 与对应 owner。
- **已落地专题**解释为什么这样做；文中的历史缺口应明确标记，不能继续冒充当前状态。
- **外部调研**记录来源、读取日期或版本、机制与适用条件；阅读公开文档不等于实测。
- **研究方向**保留候选思路，不自动成为实现计划或新 gate；具体开发方向归公开 backlog。
- **新调研**放进它服务的 feature 目录；新 feature 有两篇以上调研时才建目录，持续追踪的外部工作进 [追踪文档](research-rsi-track.md)。
