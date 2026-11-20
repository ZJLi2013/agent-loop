---
name: agent-memory
description: >-
  项目记忆：每个 git clone 一份（`.git/agent-loop/memory/`）的 INDEX / facts / episodes / lessons 四个文件，
  索引常驻、内容定向读取，写入挂在每个有意义的转换上。hook 在读 task.md 时强制注入索引。
  Use when setting up project memory, recording an outcome or a disproved hypothesis,
  looking up whether something was already tried, or when a remembered value turns out stale.
---

# Agent Memory

具体值要用时 agent 自然会去读；「这个假设是不是已经测过了」，agent 不知道自己该去查。
所以这套记忆的重心是**让检索在固定节点被迫发生**，不是存储。

**边界**：本 skill 管「后面还要用的值、结论、教训」。任务状态归 `task-state`；
单次实验的详细过程与读数归 `experiment-design`（memory 里只放它的提炼 + 链接）；
procedural memory 就是 `skills/` 本身，不在这里重复索引。

## 四个文件

**记忆属于被开发的那个项目，不属于本库。** 一个 git clone 只有一份，放在工作树之外的 git 目录里，
这个 clone 的所有工作树（`git worktree add` 出来的也算）共用；不是 git 仓库的项目放在 `.agent-loop/memory/`。
项目根没有含 `HEAD` 的 `.git` 就不算 git 仓库：monorepo 里的子项目各用自己的 `.agent-loop/memory/`，由外层 clone 跟踪，
不要往子项目根里的空 `.git/`（reviewer 沙箱的挂载点）里写：

```text
<项目>/.git/agent-loop/memory/   # linked worktree 也解析到这里；不是 git 仓库时为 <项目>/.agent-loop/memory/
  INDEX.md     # 「有什么 + 在哪」，带 anchor，不放内容。常驻，上限 30 行
  facts.md     # 当前为真的具体值。覆盖，~10 行
  episodes.md  # 跑过什么、被推翻了什么、排除了什么。追加，不设行数上限
  lessons.md   # 下次该怎么做。追加，上限 15 条
```

初始化：把 [templates/](templates/) 四个文件拷过去，删掉示例行。hook 按 cwd 解析这个路径，注入时写出它；
在哪个项目跑就读那个项目的记忆；本库自身不需要有（除非你也在长周期地开发它）。
共用同一份的工作树可能属于不同分支或工作项：只对其中一个成立的事实写明范围，改前先重读、只做局部修改。
工作树里的 `.agent-loop/memory/` 与旧 `.cursor/memory/` 在 git 项目里不再被读，hook 会告警：把仍有用的条目合并进
上面那份后删除，不能双写或分文件留在两处。

**`INDEX.md` 是这里最要紧的一个文件**：没法让 agent 去搜一个它不知道存在的东西，但可以永远把目录摆在它眼前。

## 读：hook 强制，不靠自觉

**读 `task.md` 是 SELECT 必然发生的动作**，hook 在这一刻注入，不由模型选择：

```text
读 task.md ──► hook 注入 INDEX.md + 词面命中的 0~5 条 ──► agent 继续
```

查询由 `task.md` 的 Goal 行与当前 `🔬 doing` 行组成。**命中为空会明说库存条数**，
否则脚本挂了和「这事没人试过」表现一模一样。

hook 覆盖不到的时刻（临时问一句、中途换方向），按 `INDEX.md` 的 **Retrieval hints** 列出的情境先读对应小节；
情境比「我该不该查」的判断好匹配。

读取是按 anchor 定向读，不用 embedding、向量库或 FTS：把 key-value 塞进语义检索会取回相邻的那一条，
问 node-a 的路径，返回 node-b 的。

## 写：挂在转换上，不挂在「我发现了什么」上

「我发现了一个新事实」要先意识到才会触发；转换是可观测事件，不需要意识到：

| 转换 | 写哪儿 | 不写会怎样 |
|---|---|---|
| task → `✅` | 长期结论按 `experiment-design` CLOSE 第 1 项收口到项目文档，只证明通过的验收证据留在 Experiment Log；未来检索仍需要时，`episodes.md#experiments` 留一行指针 | 长期结论埋在 Experiment Log，或两处各一份真值 |
| **假设被推翻** | `episodes.md#disproved` | **最贵也最容易丢**，下次还有人再试一遍 |
| 方案被否决 | `episodes.md#rejected` | 三周后有人重提同一个方案 |
| task → `🚧` | `episodes.md`：挡在什么上、解开条件 | 重排期时不知道它为什么还在那儿 |
| 自修成功 | `lessons.md#debugging` | 每次 OOM 都重新试那三招 |
| human 纠正你的做法（不是改任务内容） | 宿主有跨项目决策日志时写那里，不写 lessons；没有时写 `lessons.md` 并标 `[纠正]` | 同一句话 human 要对不同 agent 反复说 |
| 具体值变了 | `facts.md` **覆盖**那一行 | 就是「忘掉节点名」这个病 |
| pivot | `episodes.md`：原方向为什么放弃 | 回头有人提议走回去 |
| **看完图 / PDF / 网页** | 当场把要点落成文字 | 多模态内容不会留在上下文里，下一轮就只剩「我看过了」 |

**写内容和更新 `INDEX.md` 是一个动作，不是两步。** 只落进文件没进索引，下一轮 hook 就注入不到它。

## 收敛：只有索引有上限

只有索引常驻，所以每轮成本恒定；`episodes.md` 长到几百行也只在被定向读时进上下文。

- `INDEX.md` **超过 30 行会被忽略中段，退化成没有索引**。hook 超限告警时把条目并粗（指向小节而不是逐条），
  不靠删条目来压。
- `episodes.md` 不设统一行数上限：`experiments` 会老化，`disproved` / `rejected` 是长期决定、不老化，
  统一上限会逼着删掉最该留的那部分。

收敛的判据不是「旧」，而是「是否还会改变未来选择」。原始 evidence 留在项目 archive 与实验文档的逐 run 表，
memory 不复制。task / Goal CLOSE 时按下面顺序收敛：

1. 同一 task 的多轮成功实验最多留一条证据指针；项目文档已能直接定位结论时整条删除。
2. 被推翻的假设移到 `disproved`，被否决的方案移到 `rejected`，不再同时留在 `experiments`。
3. 当前状态、预算、排期和被覆盖决定从 episodes 删除；它们只属于 plan / `task.md`。
4. 更新 `INDEX.md` 的小节指针，不给每次实验单独建索引。

`experiments` 超过 10 条 task 级指针是漏执行 CLOSE 的告警，不是截断线；先按上述规则合并，
不能按日期删除。`current decisions` 不是 episodes 的合法小节。

## 准入与上限

`facts.md` 两条同时满足才写：**后面每轮都要用** + **重查一次要花条命令**。
据此排除结论（归 episodes）、任务状态（归 `task.md`）、以及代码里一眼能读到的东西
（写进来只会和源头漂移）。

`lessons.md` 上限 15 条，**上限是在强制筛选**。计数晋升：`[x1]` 记一次、`[x2]` 又犯、
`[x3]` 晋升为常驻 rule 并**从 lessons 删掉**——两处都留，读者不知道信哪个。
`[纠正]` 条目不走 `[x3]` 自动晋升：`[x2]` 时起草规则改动，交 reviewer 审一次后开 PR，由 human 批；合并后从 lessons 删掉。

## 验：过期比缺失更坏

新 session 开工、以及遇到「连不上 / 找不到路径 / 容器不在」时，验证接下来要用到的那几条
`facts.md`（不必验全部，一条命令能验完就验）。**过期的事实不会报错**：命令照常执行，只是打在了错的机器上，
或读了一个早被覆盖的 checkpoint。验出不对当场覆盖那一行。

调研依据与未做的部分见 [`study/memory.md`](../../docs/study/memory/memory.md)。
