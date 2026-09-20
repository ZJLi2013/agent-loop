---
name: task-loop
description: >-
  Holds the loop's durable state: the task.md schema, how to write an acceptance
  checkpoint that says what happens on failure as well as on pass, the failure
  counter that separates a first failure from a third, and the cross-session
  handoff note. Use when creating or updating task.md, picking the next task,
  writing or evaluating an acceptance checkpoint, resuming work in a new session,
  or handing off to another agent. The loop's control flow and routing live in the
  agent-loop rule; this skill owns the artifacts that loop reads and writes.
---

# Task Loop

控制流与路由在 `agent-loop` rule（常驻）。本 skill 只管它读写的那些文件。

## `task.md` 是任务状态的唯一真相源

一个项目一份，位置与 user 约定后固定。**不要另建 `tasks.json`，也不要在别处维护第二份
backlog**——两份任务状态必然漂移，而且每轮都要付一次读过期上下文的税。

```markdown
# <项目> Tasks

## Goal
<一句话：要解决什么问题。写不出来就不要往下拆。>

| P | id | task | 验收检查点 | 状态 | 失败 |
|---|---|---|---|---|---|
| P0 | t3 | 把 X 迁到 Y | `pytest tests/test_y.py` 全绿 | 🔬 doing | 1 |
| P0 | t4 | 量 Y 的端到端延迟 | p50 ≤ 基线 1.1× | ⬜ todo | 0 |
| P1 | t5 | 清理 X 的旧路径 | grep 不到 `legacy_x` | ⬜ todo | 0 |
| — | t2 | 复现 baseline | 输出与 README 同量级 | ✅ done | 0 |

<!-- 每个 task 一行。范围、方案、分析一律写在它链接的设计/实验文档里。 -->
```

**一行需要换行才读得完，就是细节没下沉。** `task.md` 每轮都被完整读一遍。

状态用 `⬜ todo / 🔬 doing / ✅ done / ❌ dropped`。`dropped` 要在行尾链接说明为什么放弃——
被否决的候选是长期决定，删掉它下次还会有人重提。

## 验收检查点：必须同时写 pass 和 fail

**只写「怎样算成功」的检查点是半个检查点。** 成功了做什么是显然的（下一个 task），
失败了做什么才是循环能不能自己转下去的关键。

一个合格的检查点满足三条：

1. **可执行或可观测**——一条命令、一个产物、一个数值阈值。「功能正常」「效果变好」不算。
2. **判据选在哪一层是明确的**——层级怎么选见 `experiment-driven-doc` 的「验收判据阶梯」。
3. **失败时的去向是已知的**——不必写在表里，但要能按 `agent-loop` 的失败分流表归类。
   归不进任何一类的失败，说明这个 task 拆得不对，回 `feature-dev-pipeline` 重拆。

写不出检查点的 task 不要开工。**这通常不是检查点难写，是这个 task 没想清楚要证明什么。**

## 失败计数

失败列记的是**这个 task 连续失败了几次**，pass 之后清零。它存在的唯一理由是让
`agent-loop` 的自修分流能分辨「第一次失败」和「已经试了三次」——没有计数，
每次失败看起来都像第一次，于是要么无限重试，要么第一次就上报。

自修一次就 +1，并在该 task 的实验文档里记一行「试了什么、结果如何」。
计数触及 `experiment-budget-gate` 的中止条件时才停。

## 跨 session 交接

`task.md` 说「做到哪了」，交接笔记说「下一步第一条命令是什么」。长任务在
`.cursor/harness/progress.md`（或与 user 约定的位置）追加：

```markdown
## YYYY-MM-DD HH:MM — <task id> <一句话状态>

当前位置：<改了什么 / 跑到哪一步>
验证：<命令 + 结果，或为什么没跑成>
下一步第一条命令：<可直接粘贴执行>
坑：<下一位 agent 会踩但从代码看不出来的>
```

**下一步要能直接粘贴执行。** 写「继续调试 Y」等于没写——接手的 agent 会重新探索一遍。

长跑还要写一份 runbook（setup / smoke / 全量 / 同步 / 清理的确切命令），
让新 session 不必重新发现环境怎么搭。

## 新 session 开工

读 `task.md` → `git status` 与近期 `git log` → 交接笔记的「下一步第一条命令」→
跑一次 runbook 里最小的 smoke。**四步都做完再动手改代码**，跳过 smoke 是
「环境早就坏了但前两小时都在改逻辑」的主要来源。

## 完成

全部 task `✅` 或剩余失败被显式接受；每个 `✅` 都有检查点的实际输出作为证据；
结论已收口到 feature 文档（见 `experiment-driven-doc`）；
新 agent 只读这些文件就能接手，不需要翻聊天记录。

然后按 `agent-loop` 走 SHIP：`code-review` → `upstream-contribute`。
