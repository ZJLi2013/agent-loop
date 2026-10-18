# Agent Loop 设计沿革

> [Study 索引](README.md) · 本文保留问题背景与演进脉络；当前架构以 [design.md](../../design.md) 为准。
> 2026-10-12 整理：历史阶段按机制归纳，不作为完整版本时间线。

## 起点：减少逐轮人工接力

最初的工作方式是 `人 → agent → 一个实验 → 人判断 → 下一个实验`。希望建立的循环是：

```text
Goal → Plan → Execute → Observe → Diagnose → Repair / Re-plan → Verify → Continue / Done
```

核心问题始终是每一步如何判断继续、换方向或停止：让 agent 能在授权范围内持续推进，
同时保留人的目标、纠偏与预算边界。研究中假设被推翻也是结果，需要据此选择下一步。

## 从规则路由到可执行边界

早期通过常驻 rule 路由 SELECT、DESIGN、EXECUTE 等步骤，再由 skill 定义具体做法。
它提供了小步任务、失败分类与人工检查点，但仅靠文字要求不能保证命令受预算限制，
也不能保证 agent 宣布完成前确实做了验证。

后续把可机械检查的条件移到 Harness：显式 runner、超时与预算、锁定 verifier、workspace
fingerprint、pause 和 Plan Revision guard。常驻 rule 继续负责路由，确定性调度和准入检查
由代码承担。详见 [最小 Harness](harness/harness.md) 与 [渐进计划](planning-review/planning-contract.md)。

宿主仍拥有未交给 runner 的工具调用；enforced adapter 依赖可拦截完成事件的宿主 hook。
持久化任务记录也不等于完整会话恢复，这些边界不能靠规则补齐。

## 从执行结果到独立判断

验证命令通过之后，还需要判断证据说明了什么，以及下一步是否值得做。worker / reviewer
分工把执行与边界判断分开：配置 reviewer 时，在 plan 提交后给出准入意见，在 task 验证后
核对证据并决定下一步。human 保留 Goal 与计划批准权。

相关依据与取舍集中在 [multi-agent 调研](planning-review/multi_agent.md)。模型选择、review 调度和权限的
当前定义归根目录设计，不在沿革中再维护一套。

## 从留下记录到可检索、可退役

跨 session 工作既需要记住已有结论，也需要避免 task、实验日志和交接快照无限增长。
因此形成了两条配套路径：

- [Memory](memory/memory.md)：在任务选择时检索，按可观察的转换写回，并维护有界索引。
- [记录生命周期](memory/experiment-record-lifecycle.md)：task / Goal 结束时合并结论、移出活跃工作集，保留证据指针和否定发现。

[心跳](harness/heartbeat.md) 则处理长任务观察：进程存在不等于有效进展，任务终态与日志变化需要分别判断。

## 外部参照与保留的取舍

[autoresearch](exploration-mode/autoresearch.md) 提供了固定预算、明确项目指标、保留或丢弃改动的参照。
它也强调失败记录应活过代码回滚。本库把这些思想放到有 Goal、review 和预算边界的通用项目循环里。

早期还关注过 [ralph](https://github.com/chrismdp/ralph) 一类在 agent 尝试退出时检查完成条件、
未完成则继续的循环方式。此处仅保留历史参考，不将其归为 Anthropic 官方方案。

本库保留扁平 task 与渐进展开，不引入 task / hypothesis DAG；checkpoint / rollback 复用 git，
不自动覆盖用户工作树。当前完整取舍见 [design.md](../../design.md)。

更广的行业对照，以及独立 radar、项目验证和 RSI 的范围，集中在
[业界实践与能力边界](industry-practices.md)。外部研究方向不自动成为本库的实现计划。
