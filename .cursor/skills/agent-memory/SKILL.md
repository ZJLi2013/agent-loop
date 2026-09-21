---
name: agent-memory
description: >-
  项目记忆：`.cursor/memory/` 下 INDEX / facts / episodes / lessons 四个文件，
  索引常驻、内容定向读取，写入挂在每个有意义的转换上。hook 在读 task.md 时强制注入索引。
  Use when setting up project memory, recording an outcome or a disproved hypothesis,
  looking up whether something was already tried, or when a remembered value turns out stale.
---

# Agent Memory

长跑里丢的不只是节点名，还有**结论**和**试过什么**。而这两类有个更难的毛病：
具体值可以「要用就读」，因为你知道自己需要节点名；**「这个假设是不是已经测过了」——
你不知道自己该去查。**

所以这套东西的重心不是存储，是**让检索在固定节点被迫发生**。

**边界**：本 skill 管「后面还要用的值、结论、教训」。任务状态归 `task-state`；
单次实验的详细过程与读数归 `experiment-design`（memory 里只放它的提炼 + 链接）；
procedural memory 就是 `.cursor/skills/` 本身，不在这里重复索引。

## 四个文件

**记忆属于被开发的那个项目，不属于本库。** agent 的持久状态统一在 `.cursor/` 下：

```text
<项目>/.cursor/
  task.md        # 任务状态（归 task-state）
  progress.md    # 交接笔记（归 task-state）
  memory/
    INDEX.md     # 「有什么」的目录，带 anchor。上限 30 行，常驻
    facts.md     # 当前为真的具体值。覆盖，~10 行
    episodes.md  # 跑过什么、被推翻了什么、排除了什么。追加
    lessons.md   # 下次该怎么做。追加，上限 15 条
```

初始化：把 [templates/](templates/) 四个文件拷过去，删掉示例行。hook 按 cwd 解析这个路径，
所以在哪个项目跑就读那个项目的记忆；本库自身不需要有（除非你也在长周期地开发它）。

**`INDEX.md` 是这里最要紧的一个文件。** 它不放内容，只放「有什么 + 在哪」——
没法让 agent 去搜一个它不知道存在的东西，但可以永远把目录摆在它眼前。
**超过 30 行它就会被忽略中段，索引本身失效**，那时和没有索引等价。

## 读：hook 强制，不靠自觉

`.cursor/hooks.json` 把 `memory-lookup.py` 挂在 `postToolUse` / `Read` 上。
**读 `task.md` 是 SELECT 必然发生的动作**，所以这一步不是模型的选择：

```text
读 task.md ──► hook 注入 INDEX.md + 词面命中的 0~5 条 ──► agent 继续
```

查询由 `task.md` 的 Goal 行与当前 `🔬 doing` 行组成。**命中为空会明说库存条数**——
索引坏了和确实没做过必须可区分，否则脚本哪天挂了，表现和「这事没人试过」一模一样。

hook 覆盖不到的时刻（临时问一句、中途换方向），靠 `INDEX.md` 里的 **Retrieval hints**：
它把「我该不该查」翻译成一串**情境**（准备跑实验 / 要改已验证的假设 / 调不熟悉的失败 /
在方案间选 / 对项目事实下断言），情境比判断好匹配。

## 写：挂在转换上，不挂在「我发现了什么」上

**「我发现了一个新事实」是判断题，要先意识到才会触发**——和「我是不是漂了」同一类毛病。
转换是可观测事件，不需要意识到：

| 转换 | 写哪儿 | 不写会怎样 |
|---|---|---|
| task → `✅` | `episodes.md#experiments`：结论一行 + 证据链接 | 结论埋在 Experiment Log，下次找不到 |
| **假设被推翻** | `episodes.md#disproved` | **最贵也最容易丢**，下次还有人再试一遍 |
| 方案被否决 | `episodes.md#rejected` | 三周后有人重提同一个方案 |
| task → `🚧` | `episodes.md`：挡在什么上、解开条件 | 重排期时不知道它为什么还在那儿 |
| 自修成功 | `lessons.md#debugging` | 每次 OOM 都重新试那三招 |
| 具体值变了 | `facts.md` **覆盖**那一行 | 就是「忘掉节点名」这个病 |
| pivot | `episodes.md`：原方向为什么放弃 | 回头有人提议走回去 |
| **看完图 / PDF / 网页** | 当场把要点落成文字 | 多模态内容不会留在上下文里，下一轮就只剩「我看过了」 |

**写内容和更新 `INDEX.md` 是一个动作，不是两步。** 只落进文件没进索引，
下一轮 hook 就注入不到它——写了等于没写。

## 上限落在哪一层

**索引有上限，内容没有——而只有索引是常驻的。** 每轮成本因此是恒定的，
`episodes.md` 长到几百行也不进上下文，只在 RETRIEVE 时被定向读。

所以真正会先出事的是 `INDEX.md`：**超过 30 行它会被忽略中段，退化成没有索引**。
hook 检测到超限会直接告警，届时把条目并粗（指向小节而不是逐条），不要靠删条目来压。

`episodes.md` **不设行数上限**，因为三段的老化速度不同：

| 段 | 老化 | 处置 |
|---|---|---|
| `experiments` | 会老化 | Goal 关闭、结论已收口到 plan document 后，这一行冗余，可剪 |
| `disproved` / `rejected` | **不老化** | 长期决定。删一条排除项，三周后就有人重提同一个方案 |

给它设统一行数上限是错的——那会逼着删掉最该留的那部分。

## 准入与上限

`facts.md` 两条同时满足才写：**后面每轮都要用** + **重查一次要花条命令**。
据此排除结论（归 episodes）、任务状态（归 `task.md`）、以及代码里一眼能读到的东西
（写进来只会和源头漂移）。

`lessons.md` 上限 15 条，**上限是在强制筛选**。计数晋升：`[x1]` 记一次、`[x2]` 又犯、
`[x3]` 晋升为 `.cursor/rules/` 里的永久规则并**从 lessons 删掉**——两处都留，读者不知道信哪个。

## 验：过期比缺失更坏

新 session 开工、以及遇到「连不上 / 找不到路径 / 容器不在」时，验证接下来要用到的那几条
`facts.md`（不必验全部，一条命令能验完就验）。

**过期的事实不会报错**：命令照常执行，只是打在了错的机器上，或读了一个早被覆盖的 checkpoint。
这类失败里很大比例根本不是环境坏了，是事实过期了。验出不对当场覆盖那一行。

## 不做检索

INDEX 带 anchor，RETRIEVE 是**定向读取**而不是搜索，所以不需要 embedding、向量库或 FTS。
本库量级下精确查找就够，而把 key-value 塞进语义检索会取回相邻的那一条——
问 node-a 的路径，返回 node-b 的。

调研依据与未做的部分见 [`study/memory.md`](../../../study/memory.md)。
