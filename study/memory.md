# Agent Memory 设计

> 调研于 2026-09，v1 已落地。这里只留关键设计与它们的理由，逐条证据见文末参考。

## 结论

**检索触发是这个领域最难的一处，而公认解法不是让 agent 更自觉，是分两层：**
能预判自己需要的放常驻层（永远在上下文，不需要检索），预判不了的放按需层，
再用一份**上限受控的常驻索引**告诉 agent 按需层里有什么。

理由是 [OpenClaw #38847](https://github.com/openclaw/openclaw/issues/38847) 那句话：

> The root cause isn't storage — memories exist on disk. It's **retrieval triggering**:
> the agent decides when to search, which means **its blind spots are also its search gaps**.

没法让 agent 去搜一个它不知道存在的东西，但可以永远把目录摆在它眼前。

## 四类记忆

[CoALA](https://arxiv.org/html/2309.02427v3) 的分法，被 2026 年几份综述沿用：

| 类型 | 内容 | 本库落点 |
|---|---|---|
| working | 当前任务状态 | `task.md` |
| semantic | 去情境化的事实 | `facts.md` |
| episodic | 发生过什么、试过什么 | `episodes.md` |
| procedural | 可复用的做法、验证过的脚本 | `skills/` 本身 |

episodic 固化成 semantic（「用户在 1/5、1/12、2/1 都改了日期格式」→「用户偏好 DD/MM/YYYY」）
**不会自动发生**，现有系统都要靠显式提示或启发式触发。计数晋升就是本库对这一步的答案。

## 三个关键设计

### 一、GATE 在 SELECT 之后、DESIGN 之前

```text
  ┌─ 常驻层：INDEX.md，记「有什么」不记「是什么」，上限 30 行 ─┐
  └────────────────────────┬──────────────────────────────┘
                           │ 每轮都在上下文
  SELECT ─► ⟦ GATE ⟧ ─► RETRIEVE ─► DESIGN ─► EXECUTE ─► EVALUATE
            这事我可能    按索引点名   带着已知                    │
            已经知道什么   去读具体文件  去设计                     │
                                                    ⟦ WRITE ⟧ ◄───┘
                                                  每个转换都写，
                                                  并同时回写索引
```

顺序是有讲究的。放在 DESIGN 之后就成了「方案都写完了才发现这事做过」，那时沉没成本已经产生，
人和 agent 都倾向于把它跑完。

这一步同时是 `experiment-design` 决策价值门的前置——那条「别处已证过的：先 grep」的规则一直
存在，但没有索引可查，所以从来没真正生效过。

### 二、写入挂在转换上，不挂在「我发现了什么」上

「我发现了一个新事实」是**判断题**，要先意识到才会触发——和「我是不是漂了」同一类毛病，
而那个自省时刻通常不会到来。**转换是可观测事件**，不需要意识到。

| 转换 | 写什么 | 不写会怎样 |
|---|---|---|
| task → `✅ CLOSE` | 结论一行 + 证据指针 | 结论埋在实验文档里，下次没人找得到 |
| **假设被推翻** | 排除项：试过 X，不行，因为 Y | **最贵的一类，也最容易丢**——下次还会有人再试一遍 X |
| task → `🚧 blocked` | 挡在什么上、解开的条件 | 重新排期时不知道它为什么还在那儿 |
| 自修成功 | 这类环境错误的修法 | 每次 OOM 都重新试一遍那三招 |
| 具体值变了 | 覆盖 `facts.md`（换节点、换 ckpt） | 就是「忘掉节点名」那个病 |
| pivot | 原方向为什么放弃 | 三周后有人提议回到原方向 |

覆盖 vs 追加分开：facts 覆盖，episodes 与排除项追加。

### 三、闭合点是「回写索引」

新知识只落进某份文档、没进 INDEX，下一轮的 GATE 就看不见它——**写了等于没写**。
所以写入与索引更新是**一个动作**，不是两步。

## v1 实现

**记忆属于工作项目，不属于本库。** agent-loop 只发模板与 hook，adapter 从事件中取得项目路径，
所以它在哪个项目跑就读那个项目的：

```text
<工作项目>/.agent-loop/memory/
  INDEX.md       # 常驻索引，带 anchor，上限 30 行
  facts.md       # 覆盖
  episodes.md    # 追加：experiments / disproved / rejected
  lessons.md     # 追加，上限 15 条，[x1]/[x2]/[x3] 晋升

agent-loop/
  skills/agent-memory/templates/       ← 四个文件的模板
  adapters/core.py                     ← 平台无关检索动作
  adapters/cursor/hooks/memory-lookup.py  ← Cursor codec
```

**GATE 做成 hook，不是规则。这是 v1 最关键的实现选择。**

```json
{ "version": 1, "hooks": { "postToolUse": [
  { "command": "python ./hooks/memory-lookup.py", "matcher": "Read", "timeout": 10 }
]}}
```

`postToolUse` 是 Cursor 唯一能返回 `additional_context` 的事件。配上 `Read` matcher 之后，
**读 `task.md`（SELECT 必然发生的动作）会无条件触发注入**，把设计从「规则要求 agent 去查」
变成「agent 没有机会不查」。写成规则的版本仍然是*让 LLM 判断自己不知道什么*，
而那恰恰是不可靠的那件事。

查询由 `task.md` 的 Goal 行 + 当前 `🔬 doing` 行组成，词面匹配三个内容文件，取前 5 条。
**无命中时明说库存条数**——空结果和索引损坏必须长得不一样。

**INDEX 里不列 skills。** name + description 每轮已在上下文（`available_skills`），
再索引一遍是付两次费，而且硬路径会随改名漂移。

### 接线的坑：hook 的 stdin 带 BOM

Cursor 在 Windows 上往 hook 的 stdin 写的是 **UTF-8 with BOM**。`sys.stdin.read()` 会保留
`\ufeff`，`json.loads` 抛 `JSONDecodeError`，脚本走兜底分支返回 `{}`——**hook 照常被调起、
退出码 0、日志显示 `returned valid response`，但注入的内容是空的**。

memory hook 从上线到 2026-09-21 一直处于这个状态。当初的验收是手动 `echo json | python`，
喂的是干净 JSON，那条路径绕开了 BOM。修法：

```python
raw = sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")
```

由此得到一条通用判据：**hook / 集成类的验收必须走真实事件**。手动喂 stdin 只测了脚本逻辑，
绕开了调用方的编码、cwd 与相对路径——这三处都出过静默失效。

**v1 未做**：CONSOLIDATE 仍是人工；hook 只覆盖 `task.md` 一个触发点；
episodes 的写入仍依赖 agent 遵守转换表，没有 hook 强制。

## 让手工清单不烂的三样东西

**上限强制筛选。** lessons 15 条 / INDEX 30 行。不设限的下场是「六周后文件 400 行，一半是
过期状态，agent 开始悄悄忽略中间那段」——索引自己超限之后，和没有索引等价。

**带计数的晋升。** `[x1]` 记一次、`[x2]` 又犯、`[x3]` 晋升为常驻规则并**从 lessons 删掉**
（两处都留会制造噪声）。这是「episodic 怎么变成 semantic」的可执行答案，不依赖模型自觉抽象。

**定期清理。** 找出反复出现或已稳定的提议晋升，同时标出过期、重复、放错层级的条目。

## 要设计进去的失败模式

- **save and pray** —— 写进去不等于读得回来。2026 年的主流失败方式是「memory 存在某处，
  agent 找不到，没人发现」。对策是查询路径本身要能报告健康度，**空结果不能等同于没有记忆**。
- **静默漏写** —— 老实更新本地进度，悄悄跳过共享知识库。修法是把两次写当成一个动作。
- **记忆与指令打架** —— 改了 rules 没改 memory，两者都进上下文互相矛盾。
- **过期胜于缺失** —— 过期事实不报错，命令照常执行，只是打在错的机器上。
- **注入过频变噪声** —— 「知道什么时候不该触发」和「知道什么时候该触发」一样难。
  挂在 session 开始与显著上下文切换，不是每轮。

## 不做：向量检索

embedding、SQLite FTS 是给跨项目几千条经验准备的。本库量级下精确查找 + 受控索引就够，
把 key-value 塞进语义检索反而会取回相邻的那一条。这个结论**只在当前 regime 成立**，
下一节就是它失效的地方。

---

## 换成个人助理：哪些前提不成立

当前设计有四个没写出来的前提：memory 挂在 repo 里因此有边界、写入由显式转换点触发、
检索 query 来自 `task.md`、库存只有几十条所以全量注入就够。换到个人助理场景**全部不成立**。

| | research（当前） | personal assistant |
|---|---|---|
| 边界 | per-project，随 repo 走 | 单一、全局、跨项目跨设备 |
| 写入触发 | 假设被推翻、值第二次用到、踩坑 | 没有转换点，信息散在日常对话里 |
| 检索触发 | 读 `task.md`，query = Goal + doing 行 | 没有 `task.md`，任何一句话都可能需要 |
| 量级 | 几十条，全量注入 | 几千到几万条，必须真检索 |
| 匹配 | substring 词面 | 语义 + 时间衰减 + 实体消歧 |
| 时效 | facts 就地覆盖 | 大量事实是时段性的，需要有效期而非覆盖 |
| 遗忘 | 人工 `[x3]` 晋升 | 必须自动去重、合并、过期 |

**最根本的一条：当前设计是拿「全量注入」代替了检索。** `INDEX.md ≤ 30 行` 这个上限、
以及「索引常驻」这个决定，只在库存小的时候成立。个人助理从第一天起就在另一个 regime，
那个上限直接失效，上面那节「不做向量检索」的结论随之翻转。

还有一条决定验收标准的结构性差别：**research memory 服务于不重复劳动**，记漏了的代价是
白烧一轮机时；**assistant memory 服务于不重复提问**，记错了的代价是信任。后者对 precision
的要求高一个量级，**记错比没记住更糟**，因此需要 research 侧完全没有的东西：
写入前的确认与冲突检测。

### 可以整块搬走的四样

**强制注入的接线方式。** 用 hook 让查询不经过模型决策——这是机制，与存什么无关。
助理版本的触发点不是「读 task.md」而是「每轮用户发言之前」，候选落点是 `beforeSubmitPrompt`。
*未核实*：文档的输出字段表没给这个事件 `additional_context`，要实测。这条线和 `task.md`
里 t7「memory hook 加第二个触发点」是同一个问题。

**索引与内容两层分离的成本模型。** 索引每轮付费、内容按需付费，这在任何规模都对。
只是助理侧的「索引」要从 30 行 markdown 换成向量库或结构化 schema。

**`#disproved` / `#rejected` 这个类别。** 「试过不行，别再试」在助理侧对应「用户说过不喜欢
X」——同样是负面偏好，同样最容易被反复冒犯，价值密度最高。

**`[x1]/[x2]/[x3]` 计数晋升。** 重复出现才升格为常驻，这是通用的信噪比控制。

### 搬不走的

facts / episodes / lessons 这个切分本身——它是研究工作的本体论，助理场景的轴是人、时间、
偏好、承诺。此外 substring 匹配、`task.md` 作为 query 来源、人工遗忘，都随前提一起失效。

**两边都要做的话，两份 memory 分开存、共用注入机制，不要合成一份。**
写入触发、容量量级、时效模型三者都不同。

## 参考

- [CoALA](https://arxiv.org/html/2309.02427v3) —— 四类记忆的来源
- [Memory for Autonomous LLM Agents](https://arxiv.org/abs/2603.07670v1) —— 2022–2026 综述，write–manage–read 循环
- [A Survey of Agent Memory in the Second Half](https://arxiv.org/html/2602.06052v4)
- [Letta：Memory Blocks](https://www.letta.com/blog/memory-blocks/) 与 [Archival memory](https://docs.letta.com/v1-sdk/memory/archival-memory/index.md) —— 两层切分的参照实现
- [Anthropic：context editing 与 memory tool](https://www.anthropic.com/news/context-management) —— memory + context editing 比 baseline +39%
- [OpenClaw #38847](https://github.com/openclaw/openclaw/issues/38847) —— 检索触发才是根因
- [三文件系统（Law / State / Wisdom）](https://dev.to/won_ztw/the-three-file-system-that-fixed-claude-codes-amnesia-across-11-projects-23ga) —— 按变更频率分层，压缩策略互斥
- [ADR-003：memory 与 harness 的边界](https://github.com/phasespace-labs/palinode/commit/6bd5d2aade677d42e8c224c0943fd85c52998e92) —— save and pray
- [proactive memory：什么时候不该触发](https://mem0.ai/blog/proactive-memory-in-ai-agents-a-developer-s-guide)
