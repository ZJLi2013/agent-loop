# Skills Index

Skills are the **Policies** layer defined in [`design.md`](../../design.md): each one explains how to act in a
specific state. They do not redefine state transitions, runtime guards, or another skill's document format.

```text
.cursor/skills/<skill-name>/SKILL.md
```

## Loop policies

Descriptions stay in context; bodies load only when the current event matches.

| Skill | Owns |
|---|---|
| `work-planning` | Goal → plan document → proposed task → review；Goal Review 与 RECONCILE |
| `task-state` | `task.md` schema、检查点、失败计数、交接 |
| `experiment-design` | 实验假设、决策门、验收阶梯、exp 记录 |
| `agent-memory` | facts / episodes / lessons 的准入、检索与写回 |
| `agent-heartbeat` | 超过 60 秒命令的进度与心跳 |

状态、事件和 guard 归 `harness/protocol.py`；常驻 `agent-loop` rule 只把状态路由到上表。

## Explicit / cold policies

只在 user 点名时加载：

- `remote-exec`：远端节点、detach、传输、存储与环境自修。
- `code-review`：本地 diff / PR review 标准。
- `code-to-kernel-diagram`：模块到 kernel 数据流。
- `upstream-contribute`：上游 PR / Issue 判断与正文。
- `research-to-blog`：调研到对外文章。

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
| Cursor 事件接线 | `.cursor/hooks/` |

Bugbot 不读 rules 或 skills。PR 上的 review 标准只能放目标 repo 的 `.cursor/BUGBOT.md` 或
Cursor dashboard Team / Repository Rules。

## Adding behavior

按 [`design.md`](../../design.md) 的 extension rule 判断：

1. 项目差异 → config / profile；
2. 某状态下怎么做 → 现有 owner skill；
3. 平台接线 → adapter / hook；
4. 只有新生命周期状态、事件或不可绕过 guard 才改 Kernel。

新增段落必须删除被替代路径。不要用另一个 skill 重述相同流程；长 runbook 放 `reference.md`，
可复用命令放 `scripts/`。
