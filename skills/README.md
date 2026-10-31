# Skills Index

Skills are the **Policies** layer defined in [`design.md`](../design.md): each one explains how to act in a
specific state. They do not redefine state transitions, runtime guards, or another skill's document format.

```text
skills/<skill-name>/SKILL.md
```

## Loop policies

Descriptions stay in context; bodies load only when the current event matches.

| Skill | Owns |
|---|---|
| `work-planning` | Goal → plan document → proposed task → review；Goal Review、RECONCILE 与 task / Goal CLOSE |
| `task-state` | 活跃 `task.md`、closed-task archive、检查点、失败计数、当前交接快照 |
| `experiment-design` | 实验假设、决策门、验收阶梯、单轮 exp 记录、verifier 前 CLOSE self-audit |
| `agent-memory` | facts / episodes / lessons 的准入、检索、写回与去重 |
| `agent-heartbeat` | detach 长任务的连接与日志心跳 |
| `self-report` | agent-loop 自身缺陷的归因、去重、发布前检查与 issue 上报 |
| `code-to-uml-diagram` | 类级设计的现状 / 目标类图与按场景的时序图（`work-planning` 第 2 步触发） |

状态、事件和 guard 归 `harness/protocol.py`；常驻 `agent-loop` rule 只把状态路由到上表。

领域或个人的 skill 不在本仓库，放进自己的包，见[安装 skill 包](../docs/usage.md#skill-packs)。

## Ownership

一个知识点只有一个 owner；其它位置只留链接或一句 guard。

| 知识点 | Owner |
|---|---|
| 状态、事件、合法转移 | `harness/protocol.py` |
| Goal、review、revision、attention refresh、人工纠偏 | `work-planning` |
| task schema 与检查点 | `task-state` |
| 实验设计与 exp 文档 | `experiment-design` |
| 自修上限、预算与中止 | `when-to-stop` rule |
| 人类可读输出 | `write-for-humans` rule |
| 对外披露 / 脱敏 / 去私料 | `external-output-boundary` rule |
| Harness runtime / evidence | `harness/` |
| task 边界 reviewer 的 prompt 与决策格式 | `harness/prompts/task_review.md`（校验在 `harness/review.py`） |
| plan reviewer 的 prompt、报告与 revision 去重 | `harness/prompts/plan_review.md`（校验与去重在 `harness/plan_review.py`） |
| 平台事件接线 | `adapters/<platform>/` |

Bugbot 不读 rules 或 skills。PR 上的 review 标准只能放目标 repo 的 `.cursor/BUGBOT.md` 或
Cursor dashboard Team / Repository Rules。

## Adding behavior

按 [`design.md`](../design.md) 的 extension rule 判断：

1. 项目差异 → config / profile；
2. 某状态下怎么做 → 现有 owner skill；
3. 平台接线 → adapter / hook；
4. 只有新生命周期状态、事件或不可绕过 guard 才改 Kernel。

新增段落必须删除被替代路径。不要用另一个 skill 重述相同流程；长 runbook 放 `reference.md`，
可复用命令放 `scripts/`。
