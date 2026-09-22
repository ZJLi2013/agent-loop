---
name: task-state
description: >-
  维护 task.md：验收检查点（同时写失败去向）、失败计数、只有一行 doing 的防漂移不变量、
  跨会话交接笔记。循环本身归 agent-loop rule。
  Use when creating or updating task.md, picking the next task, writing an acceptance
  checkpoint, or resuming work in a new session.
---

# Task State

控制流与路由在 `agent-loop` rule（常驻）。本 skill 只管它读写的那些文件。

## `task.md` 是任务状态的唯一真相源

一个项目一份，放在 **`.agent-loop/task.md`**——和 `.agent-loop/memory/`、`.agent-loop/progress.md` 同一个
home，也避开仓库自带的 `task.md` / `TODO.md`。**不要另建 `tasks.json`，也不要在别处维护第二份
backlog**——两份任务状态必然漂移，而且每轮都要付一次读过期上下文的税。

```markdown
# <项目> Tasks

## Goal
<一句话：要解决什么问题。写不出来就不要往下拆。>

| P | id | rev | task | 验收检查点 | 状态 | 失败 |
|---|---|---|---|---|---|---|
| P0 | t7 | r2 | 把 X 迁到 Y | `pytest tests/test_y.py` 全绿 | 📝 proposed | 0 |
| P0 | t3 | r1 | 把 X 迁到 Y | `pytest tests/test_y.py` 全绿 | 🚧 blocked t6 | 1 |
| P0 | t6 | r2 | 修 Y 的 schema 漂移 | `validate.py` 退出码 0 | 🔬 doing | 0 |
| P0 | t4 | r2 | 量 Y 的端到端延迟 | p50 ≤ 基线 1.1× | ⬜ todo | 0 |
| P1 | t5 | — | 清理 X 的旧路径 | grep 不到 `legacy_x` | ⬜ todo | 0 |
| — | t2 | — | 复现 baseline | 输出与 README 同量级 | ✅ done | 0 |

<!-- 每个 task 一行。范围、方案、分析一律写在它链接的设计/实验文档里。 -->
```

**一行需要换行才读得完，就是细节没下沉。** `task.md` 每轮都被完整读一遍。

状态用 `📝 proposed / ⬜ todo / 🔬 doing / 🚧 blocked <id> / ✅ done / ❌ dropped`。
`proposed` 表示还在 Human Review Gate，批准前不执行；`dropped` 要在行尾链接说明为什么放弃——
被否决的候选是长期决定，删掉它下次还会有人重提。

`rev` 把 task 绑定到 plan document 的 `Plan Revision: N`，写作 `rN`；不属于 plan
的维护项写 `—`。human 修改 Goal 后 revision 必须递增，旧 revision 的 task 逐项 blocked / dropped，
不能继续执行。

等待 review 时允许「若干 `📝 proposed` + 零行 doing」；除此之外，**`🔬 doing` 有且只有一行。**
批准时最高优先级 proposed 转 doing，其余转 todo。跑到一半要改别的东西时，先挪 `🔬`
（原行转 blocked 并记下挡它的 id）。**`🚧` 的个数就是嵌套深度，≥ 2 停下问人。**

**具体的值不写进 `task.md`。** 远端节点、容器名、checkpoint 路径这类跨会话还要用的常量，
归 `agent-memory` 的 `.agent-loop/memory/facts.md`——那份就地覆盖，这份记任务状态，两种写法不混。

## 验收检查点：必须同时写 pass 和 fail

**只写「怎样算成功」的检查点是半个检查点。** 成功了做什么是显然的（下一个 task），
失败了做什么才是循环能不能自己转下去的关键。

一个合格的检查点满足三条：

1. **可执行或可观测**——一条命令、一个产物、一个数值阈值。「功能正常」「效果变好」不算。
2. **判据选在哪一层是明确的**——层级怎么选见 `experiment-design` 的「验收判据阶梯」。
3. **失败时的去向是已知的**——不必写在表里，但要能按 `agent-loop` 的失败分流表归类。
   归不进任何一类的失败，说明这个 task 拆得不对，回 `work-planning` 重拆。

再做一步长检查：**一个 task 最多跨越一个未验证假设。** 如果通过要同时赌两件事，或失败后
无法判断哪条假设错了，就把 inspection / probe 拆成前一项。只把最近 1–2 个增量项写进表，
远期路线留在 plan document；每项变绿后再生成下一项。

写不出检查点的 task 不要开工。**这通常不是检查点难写，是这个 task 没想清楚要证明什么。**

写成「重构干净」「跑通」的检查点有双重代价：**既判不出完成，也挡不住漂移**——
任何改动都能说自己在往那个方向走（`agent-loop` 的漂移判据要拿这个检查点当尺子）。

## 失败计数

失败列记的是**这个 task 连续失败了几次**，pass 之后清零。它存在的唯一理由是让
`agent-loop` 的自修分流能分辨「第一次失败」和「已经试了三次」——没有计数，
每次失败看起来都像第一次，于是要么无限重试，要么第一次就上报。

自修一次就 +1，并在该 task 的实验文档里记一行「试了什么、结果如何」。
计数触及 `when-to-stop` 的中止条件时才停。

## 跨 session 交接

三份东西分工不同，**区别在追加还是覆盖**：

| 文件 | 内容 | 写法 | 归属 |
|---|---|---|---|
| `.agent-loop/memory/facts.md` | 现在该用哪个节点 / 容器 / 路径 | **覆盖**，只有当前值 | `agent-memory` |
| `task.md` | 做到哪了、哪条被挡住 | 改状态列 | 本 skill |
| `.agent-loop/progress.md` | 这一轮发生了什么、下一步第一条命令 | **追加**，带时间戳 | 本 skill |

**具体的值不要只写进交接笔记**——它按时间追加，三天后就被后面的记录埋掉，
这正是「跑久了忘掉节点名」的成因。

交接笔记的格式：

```markdown
## YYYY-MM-DD HH:MM — <task id> <一句话状态>

当前位置：<改了什么 / 跑到哪一步>
验证：<命令 + 结果，或为什么没跑成>
下一步第一条命令：<可直接粘贴执行>
坑：<下一位 agent 会踩但从代码看不出来的>
```

**下一步要能直接粘贴执行。** 写「继续调试 Y」等于没写——接手的 agent 会重新探索一遍。

Human 纠偏的 pause → revision → RECONCILE → resume 事务归 `work-planning`；本 skill
只执行它给出的行状态变更，不重新定义顺序。

长跑还要写一份 runbook（setup / smoke / 全量 / 同步 / 清理的确切命令），
让新 session 不必重新发现环境怎么搭。

## 新 session 开工

读 `task.md` → 读 `.agent-loop/memory/facts.md` 并**验证接下来要用到的那几条**（见 `agent-memory`）
→ `git status` 与近期 `git log` → 交接笔记的「下一步第一条命令」→ 跑一次 runbook 里最小的 smoke。

**五步都做完再动手改代码。** 跳过验证与 smoke 是「环境早就坏了但前两小时都在改逻辑」的
主要来源。

## 完成

全部 task `✅` 或剩余失败被显式接受；每个 `✅` 都有检查点的实际输出作为证据；
结论已收口到 plan document（见 `work-planning`）；
新 agent 只读这些文件就能接手，不需要翻聊天记录。

**满足这四条就是 DONE：报告结果然后停。** 评审、提上游、写博客都是 user 要了才做的岔出项，
不是循环的出口（见 `agent-loop` 的「岔出」）。
