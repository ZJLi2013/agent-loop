# Agent Memory 调研

> 调研时间 2026-09。目的：判断本库的 `agent-memory` 该做成什么样。

## 结论

**本库当前的 `facts.md` 覆盖四类记忆里的一类，并且缺了业界解决「不知道该去查」的那个关键件——
常驻索引。**

检索触发是这个领域最难的一处，而它的公认解法不是让 agent 更自觉，而是**分两层**：
能预判自己需要的东西放常驻层（永远在上下文里，不需要检索），预判不了的放按需层，
再用一份**上限受控的常驻索引**告诉 agent 按需层里有什么。没有索引，agent 的盲区
就等于它的检索盲区。

## 目标形状

```text
                  ┌─────────────────────────────────┐
                  │   META MEMORY  · 常驻            │
                  │   记「有什么」，不记「是什么」      │
                  │   上限 ~30 行，超了就没人读        │
                  └────────────────┬────────────────┘
                                   │ 每轮都在上下文里
  ═════════════════════════════════╪═══════════════════════════════
                                   ↓
   GOAL ─► PLAN ─► SELECT ─►  ⟦ MEMORY GATE ⟧
                              这件事我可能已经知道什么？
                                   ↓
                               RETRIEVE          按索引点名去读
                                   ↓
                                DESIGN           带着已知去设计
                                   ↓
                               EXECUTE ◄───────────────┐
                                   ↓                   │
                               EVALUATE                │
                              ╱        ╲               │
                          pass          fail           │
                           ↓              ↓            │
                         CLOSE         DIAGNOSE        │
                           │              ↓            │
                           │        repair / replan ───┘
                           │              │
                           └──────┬───────┘
                                  ↓
                        ⟦ MEMORY WRITE ⟧
                    每个有意义的转换都写，
                    不只在「我发现了一个事实」时
                                  ↓
                        ⟦ CONSOLIDATE? ⟧
                    第 n 次重复 → 晋升为 FACT / SKILL / 规则
                                  ↓
  ═════════════════════════════════════════════════════════════════
                         回写 META MEMORY
                                  ↓
                             next task
```

### GATE 在 SELECT 之后、DESIGN 之前

**顺序是有讲究的**：先查再设计，设计才能带着已知走；放在 DESIGN 之后就成了
「方案都写完了才发现这事做过」，那时沉没成本已经产生，人和 agent 都倾向于把它跑完。

这一步同时是决策价值门的前置：**查完才知道这轮是不是「别处已证过的」**——
`experiment-design` 里那条规则一直存在，但没有索引可查，所以从来没真正生效过。

### 写入挂在转换上，不挂在「我发现了什么」上

这是关键的一处。「我发现了一个新事实」是**判断题**，要先意识到才会触发——
和「我是不是漂了」同一类毛病，而那个自省时刻通常不会到来。
**转换是可观测事件**，不需要意识到。

| 转换 | 写什么 | 不写会怎样 |
|---|---|---|
| task → `✅ CLOSE` | 结论一行 + 证据指针 | 结论埋在 exp 文档里，下次没人找得到 |
| **假设被推翻** | 排除项：试过 X，不行，因为 Y | **最贵的一类，也最容易丢**——下次还会有人再试一遍 X |
| task → `🚧 blocked` | 挡在什么上、解开的条件 | 重新排期时不知道它为什么还在那儿 |
| 自修成功 | 这类环境错误的修法 | 每次 OOM 都重新试一遍那三招 |
| 具体值变了 | 覆盖 FACT（换节点、换 ckpt） | 就是现在这个「忘掉节点名」的病 |
| pivot | 原方向为什么放弃 | 三周后有人提议回到原方向 |

覆盖 vs 追加照旧分开：FACT 覆盖，EPISODE 与排除项追加。

### 闭合点在「回写索引」

新知识只落进某份文档、没进 META MEMORY，下一轮的 GATE 就看不见它——**写了等于没写**，
也就是第五节的 save and pray。所以 MEMORY WRITE 与索引更新要当成**一个动作**，
不是两步（第五节「静默漏写」那条）。

### 每个节点对应到本库

| 节点 | 现状 | 缺口 |
|---|---|---|
| META MEMORY | **没有** | 最实质的缺口：没有索引，GATE 无从判断 |
| MEMORY GATE | `experiment-design` 有「别处已证过的：先 grep」 | 规则在、位置也对，但无索引可查，从未真正生效 |
| RETRIEVE | feature 文档、`partN-exp.md`、结论速查 | 存储齐全，缺的是「按什么去点名」 |
| EXECUTE / EVALUATE / DIAGNOSE | `agent-loop` 齐全 ✅ | — |
| MEMORY WRITE | 只有 CLOSE 那一条（回填 feature 文档） | **其余五类转换全都没有写入点**，尤其是被推翻的假设 |
| CONSOLIDATE | **没有** | 计数晋升（`[x1]`/`[x2]`/`[x3]`）是候选机制 |
| FACT | `.cursor/memory/facts.md` ✅ | 只覆盖运行环境常量，不含结论 |
| SKILL | `.cursor/skills/` ✅ | 由人维护，agent 不自写 |

**按缺口的严重度排，要做的顺序是**：META MEMORY（没有它后面都是空转）→ 六类转换的写入点
→ CONSOLIDATE 的晋升计数。GATE 本身几乎不用改，它一直在那儿等一个能查的索引。

### v1 已落地（2026-09）

四个文件 + 一个 hook，procedural 直接复用 `.cursor/skills/`。

**记忆属于工作项目，不属于本库。** my_skills 只发模板与 hook，`.cursor/memory/`
在每个项目里各有一份——脚本按 cwd 解析，所以它在哪个项目跑就读那个项目的：

```text
<工作项目>/.cursor/memory/          ← 每个项目一份，由 templates 拷出
  INDEX.md       # META MEMORY，带 anchor，上限 30 行
  facts.md       # 覆盖
  episodes.md    # 追加：experiments / disproved / rejected
  lessons.md     # 追加，上限 15 条，[x1]/[x2]/[x3] 晋升

my_skills/.cursor/
  skills/agent-memory/templates/   ← 四个文件的模板
  hooks/memory-lookup.py           ← 机制，装到 ~/.cursor/hooks/ 全局生效
```

**GATE 做成了 hook，不是规则。** 这是 v1 最关键的实现选择：

```json
{ "version": 1, "hooks": { "postToolUse": [
  { "command": "python ./hooks/memory-lookup.py", "matcher": "Read", "timeout": 10 }
]}}
```

`postToolUse` 是 Cursor 唯一**能返回 `additional_context`** 的事件，配 `Read` matcher 之后，
**读 `task.md`（SELECT 必然发生的动作）会无条件触发注入**。这把设计从
「规则要求 agent 去查」变成「agent 没有机会不查」——写成规则的版本仍然是
*LLM 判断自己不知道什么*，而这恰恰是第二节说不可靠的那件事。

查询由 `task.md` 的 Goal 行 + 当前 `🔬 doing` 行组成，词面匹配 `episodes` / `lessons` / `facts`，
取前 5 条。**无命中时明说库存条数**——落实第五节那条：空结果不能和索引损坏长得一样。

实测：task 写「测 noise aug 对 shift 的影响」，hook 顶出了
`disproved` 里的「noise aug 能改善 shift → 所有 sigma 都变差」。这正是要拦的那一类。

**INDEX 里不列 skills。** skill 的 name + description 每轮已经在上下文里（`available_skills`），
再索引一遍是付两次费，而且硬路径会随改名漂移——2026-09 一天内就改了三次名。

**v1 未做**：CONSOLIDATE 仍是人工（`[x3]` 晋升靠自己动手）；hook 只覆盖 `task.md` 这一个
触发点，DESIGN 阶段拿假设再查一次没做；episodes 的写入仍依赖 agent 遵守转换表，
没有 hook 强制。

---

## 一、四类记忆

[CoALA](https://arxiv.org/html/2309.02427v3) 的分法被 2026 年几份综述沿用：

| 类型 | 内容 | 本库现状 |
|---|---|---|
| working | 当前任务状态 | `task.md` |
| semantic | 去情境化的事实 | `facts.md` ✅ |
| **episodic** | 发生过什么、试过什么 | ❌ |
| **procedural** | 可复用的做法、验证过的脚本 | ❌ |

「之前这个假设测过了吗」横跨 episodic 与 semantic 的**固化**过程，而
[Memory for Autonomous LLM Agents](https://arxiv.org/abs/2603.07670v1) 指出这个固化不自动发生：

> Semantic memory. An episodic fact like "the user corrected the date format on Jan 5, Jan 12, and
> Feb 1" may consolidate into the semantic record "user prefers DD/MM/YYYY."
> **This consolidation is rarely automatic; most current systems require explicit prompting or
> heuristic triggers.**

procedural 的典型实现是 Voyager 的 skill library：每个验证过的例程存成可运行代码，
用自然语言描述索引，按需组合。**本库的 skills 本身就是 procedural memory**，
只是它由人维护、不由 agent 自己写。

## 二、检索触发：盲区就是检索盲区

[OpenClaw #38847](https://github.com/openclaw/openclaw/issues/38847) 说得最干脆：

> The root cause isn't storage — memories exist on disk. It's **retrieval triggering**:
> the agent decides when to search, which means **its blind spots are also its search gaps**.

同一个观察在 RAG 那边的说法是「the agent doesn't know what it doesn't know — it can't decide to
retrieve more if it already answered from stale context」。

### 两层切分，按「能不能预判需要它」

| 系统 | 常驻层 | 按需层 |
|---|---|---|
| [Letta / MemGPT](https://www.letta.com/blog/memory-blocks/) | core memory blocks，永远在上下文，**不需要检索**；agent 用 `memory_insert` / `memory_replace` / `memory_rethink` 自编辑 | archival，必须调 `archival_memory_search`（语义检索 + tag） |
| Claude Code Auto Memory | `MEMORY.md` 索引，自动加载，**上限 200 行** | `debugging.md` / `api-conventions.md` 等主题文件 |
| [Anthropic memory tool](https://www.anthropic.com/news/context-management) | 开工前自动扫 `/memories` 目录 | 目录里的具体文件 |

**关键件是那个常驻索引。** 没法让 agent 去搜一个它不知道存在的东西，但可以永远把目录摆在它
眼前——看到有 `debugging.md`，它就知道该翻。Letta 把这一层描述为
"always visible - no retrieval needed"，archival 则 "must be queried on-demand via tools"。

### 注入频率

[mem0 的总结](https://mem0.ai/blog/proactive-memory-in-ai-agents-a-developer-s-guide)：每轮都注入会变成噪声，
**「知道什么时候不该触发」和「知道什么时候该触发」一样难**。建议限到 session 开始 +
显著上下文切换，不是每轮。OpenClaw 的 Active Memory 默认是 `escalate` 模式：
只在消息确实在问过去、且确定性检索没命中时，才起阻塞式的深检索子 agent。

## 三、编码 agent 的实践：三个文件，按变更频率分层

多个来源独立收敛到同一组：

| 层 | 文件 | 变更 | 压缩 |
|---|---|---|---|
| 律法 | `CLAUDE.md` / rules | 很少，刻意 | 永不 |
| 状态 | `PROGRESS.md` | 每轮 | 24h 后压 |
| **经验** | **`LESSONS.md`** | 被纠正时 | 永不 |

[三文件那篇](https://dev.to/won_ztw/the-three-file-system-that-fixed-claude-codes-amnesia-across-11-projects-23ga)
的理由是这三者压缩策略互斥：

> Put them in one file and there is no setting that works. Compress aggressively and you shred your
> hard-won lessons. Don't compress and you bleed tokens forever.

对照本库：律法有（`.cursor/rules/`）、状态有（`task.md` + `.cursor/progress.md`）、
**经验这层完全没有**。

## 四、让手工清单不烂的三样东西

裸清单会腐化，实践里靠这三条撑住：

**上限强制筛选。** lessons 15 条 / memory 文件 80 行 / `MEMORY.md` 200 行。
不设限的下场：「六周后文件 400 行，一半是过期状态，agent 开始悄悄忽略中间那段」。

**带计数的晋升机制。** `[x1]` 记一次、`[x2]` 又犯、`[x3]` 晋升为永久规则并**从 lessons 删掉**
（两处都留会制造噪声）。这是「episodic 怎么变成 semantic」的一个可执行答案，
不依赖模型自觉抽象。日期前缀同理有用：两周前没再犯的可以剪，昨天的还烫手。

**定期清理动作。** 有人做成 `/reflect` 命令：读 lessons 与 log，找出反复出现或已稳定的，
提议晋升，同时标出过期、重复、放错层级的条目。

## 五、要设计进去的失败模式

- **save and pray** —— 写进去不等于读得回来。
  [ADR-003](https://github.com/phasespace-labs/palinode/commit/6bd5d2aade677d42e8c224c0943fd85c52998e92)
  说这是 2026 年的主流失败方式：「memory 存在某处，agent 找不到，没人发现」。
  对策是 session 开始时先查 memory 子系统的健康（索引是否落后于文件），
  **空结果不能等同于「没有记忆」**。
- **静默漏写** —— agent 老实更新本地进度，悄悄跳过共享知识库。
  修法：把两次写当成一个动作，报告前自检两边都写了。
- **记忆与指令打架** —— 改了 rules 没改 memory，两者都进上下文互相矛盾。
  改指令时要同步标记或删除过期的记忆条目。
- **过期胜于缺失** —— 过期事实不报错，命令照常执行只是打在错的机器上。
- **索引膨胀** —— 索引自己超限之后，和没有索引等价。

## 六、对本库的含义

**结论已经有存储了，缺的是索引和读取触发。** `experiment-design` 规定结论收口在 feature 文档，
`feature-planning` 里有「结论速查」区——存储在那儿。但没有任何机制让 agent 在开跑一轮实验前
去查一下「这个假设是不是已经有答案了」。这和第二节是同一个诊断。

据此，下一版 `agent-memory` 至少要回答三件事：

1. **常驻索引放哪、上限多少。** 它必须小到每轮都读得起。
2. **episodic 怎么写、什么时候固化。** 计数晋升是个候选；`when-to-stop` 已有
   「同一个问题连续两轮答案相同 → 降优先级」这类计数习惯，可以接上。
3. **开跑前查一次的触发挂在哪。** `experiment-design` 的决策价值门里已经有一条
   「别处已证过的：先 grep 已有文档」——那条规则存在但没有被索引支撑，所以基本不生效。

不做的：向量检索、embedding、SQLite FTS。那是给跨项目积累几千条经验准备的；
本库的量级下精确查找 + 受控索引就够，而把 key-value 塞进语义检索会取回相邻的那一条。

## 参考

- [Cognitive Architectures for Language Agents (CoALA)](https://arxiv.org/html/2309.02427v3) —— 四类记忆的来源
- [Memory for Autonomous LLM Agents: Mechanisms, Evaluation, and Emerging Frontiers](https://arxiv.org/abs/2603.07670v1) —— 2022–2026 综述，write–manage–read 循环
- [A Survey of Agent Memory in the Second Half](https://arxiv.org/html/2602.06052v4) —— substrate / mechanism / subject 三维分类
- [Letta：Memory Blocks](https://www.letta.com/blog/memory-blocks/) 与 [Archival memory](https://docs.letta.com/v1-sdk/memory/archival-memory/index.md)
- [Anthropic：context editing 与 memory tool](https://www.anthropic.com/news/context-management) —— memory + context editing 比 baseline +39%
- [三文件系统（Law / State / Wisdom）](https://dev.to/won_ztw/the-three-file-system-that-fixed-claude-codes-amnesia-across-11-projects-23ga)
- [lessons.md 与 log.md 的分工](https://palette.team/articles/how-we-gave-our-agents-memory)
- [ADR-003：memory 与 harness 的边界](https://github.com/phasespace-labs/palinode/commit/6bd5d2aade677d42e8c224c0943fd85c52998e92)
- [proactive memory：什么时候不该触发](https://mem0.ai/blog/proactive-memory-in-ai-agents-a-developer-s-guide)
