# 探索模式：agent 怎样推进开放研究问题（提案）

> 2026-10-12 提案。外部机制来自下文列出的一手论文与文档，读取于同日；未运行这些系统。
> 本文是研究方向，不是实现计划或新 gate；导航见 [Study 索引](README.md)，当前架构见 [design.md](../design.md)。

## 结论

**探索与确认是两种模式，不变量正好相反；agent-loop 现有的环是确认模式。** 单线 task、plan revision、锁定 verifier 和准入式 reviewer 的作用是压住漂移，这让工程迭代有效，也让开放问题退化成"下一个最便宜候选"的随机游走。开放问题的瓶颈往往不是文献，而是**还没有一个能衡量进展的信号**；探索模式的产出就是造出这个信号，并把问题收窄成可确认的假设，再交给 agent-loop。

建议先在本仓以独立模式落地：一份 policy、一个研究地图模板、时间盒预算和几条反模式告警；复用 runner、心跳与 memory，不改 Harness 的 gating。需要多分支并行编排时再评估拆成独立系统。

## 问题：一个开放问题怎样被推成随机游走

案例是 roboJev Stage 1.5（具身 option 层 typed decision 的价值验证，前序案例见 [plan 增长](../case_study/robojev-plan-growth.md)）：

- **r37–r60 共 24 个 revision 经过独立 plan review**，跨 3 天；载体 A 上三个候选依次关闭，每一步都在回答"下一个最便宜的候选是什么"。
- **载体本身直到 r53 才被质疑**：执行器读仿真真值、原生几乎不失败，任何选择价值都只能来自人为扰动——这是后续所有候选共享的前提，却从未作为一条分支与其他载体并列比较。
- **2026-10-12 的 r53–r60 共 8 个 revision、0 个实验**：reviewer 每轮提出的协议问题都成立（真值隔离、seed 分块、示意数值自洽），但被审对象是一个 ≤ 20 分钟的采样前置。

三个机制原因：

1. **没有问题地图**：状态只有 plan 与单行 doing，无法表达"同一根问题下的多种切入方式"，也就无法比较、剪枝或判断离答案还有多远。
2. **门槛与成本不相称**：reviewer 优化协议严谨性与准入，不评估"这是不是信息量最大的下一步"；对低成本探针，流程成本超过实验成本。
3. **只有一种推进单位**：一切都是 task，都要过 plan / review / verifier，没有"跑一小时就扔"的轻量通道。

## 业界做法：按是否有自动评估器分两类

| 系统 | 机制 | 适用前提 |
|---|---|---|
| [autoresearch](https://github.com/karpathy/autoresearch) | 固定训练预算与 `val_bpb`，改动改善则保留、否则回滚（见 [autoresearch](autoresearch.md)） | 已有单一可测目标 |
| [AlphaEvolve](https://arxiv.org/abs/2506.13131) | LLM 提出程序变体，用户提供的评估函数打分，进化搜索 | 必须有自动评估器；原文把需要人工实验的问题列为范围之外，并指出需要全新深刻洞见的问题"可能不是合适工具"（[2511.02864](https://arxiv.org/abs/2511.02864)） |
| [AI Scientist-v2](https://arxiv.org/abs/2504.08066) | 实验管理 agent 分四阶段（初步实现、baseline 调优、创造性研究、消融）推进并行 best-first 树搜索，每阶段最佳节点作为下一阶段起点 | 实验可在代码里执行并自动产出结果的 ML 问题 |
| [AI co-scientist](https://www.nature.com/articles/s41586-026-10644-y) | Generation / Reflection / Ranking（Elo 锦标赛与模拟辩论）/ Evolution / Proximity / Meta-review 多 agent 迭代；科学家设定目标并持续引导 | 没有自动评估器；产出是排序后的假设与研究方案，实验由人执行 |

两条规律：

- **有评估器时靠搜索，没有评估器时靠"多分支 + 判断力排序 + 人在环"。** 后者不是单线推进，而是先发散、再按质量与可检验性排序、再收敛。
- **没有评估器时，第一件事是造评估器。** AlphaEvolve 的开发指南写明：没有可自动计算的目标时，问题"尚未准备好"，核心任务是先构造代理函数或仿真（[Quantify the optimization target](https://docs.cloud.google.com/gemini/enterprise/docs/alphaevolve/developer-guide/quantify-optimization-target)）。roboJev 缺的正是这一步：在搭 selector 与感知之前，没有先测"按状态选 option"的收益上限。

## 探索模式的设计

### 不变量：与确认模式对照

| | 探索模式 | 确认模式（agent-loop 现有） |
|---|---|---|
| 推进单位 | probe：时间盒内完成，允许粗糙代码，用完即弃 | task：设计文档 + 锁定 verifier |
| 状态载体 | 研究地图：问题树、分支、证伪条件、上限估计、状态 | plan document + revision；`task.md` 唯一 doing |
| 并行度 | 同一周期内多个 probe 并行 | 单线 |
| 失败的含义 | 剪掉一个分支，是产出 | 进入 DIAGNOSE / 失败计数 |
| reviewer 审什么 | 框架与价值：是否信息量最大、是否漏了竞争性切入 | 协议严谨性与准入 |
| human 介入 | 每个时间盒结束时剪枝、提升 | 批准 plan、纠正 Goal |
| 出口 | 某分支提升为 agent-loop Goal | done / stop / human |

### 研究地图

探索模式唯一的状态载体，是一份文档，不是调度器里的 DAG：

```markdown
# <根问题>

## 根问题与价值
<一句话；答案为是 / 否时分别会做什么>

## 分支
| id | 切入方式 | 为什么可能成立 | 进展信号（评估器 / 代理） | 上限估计 | 最便宜的决定性 probe | 证伪条件 | 预算 | 状态 |

## 已剪掉
| id | 剪枝理由 | evidence |

## 时间盒记录
| 周期 | 跑了哪些 probe | 地图改变了什么 | 下一周期 |
```

每个 probe 结束只回答一件事：**地图改变了什么**——剪掉、提升，或改变了某分支的上限估计。说不出改变就是零信息 probe。

### 一个探索周期

1. **发散**：对根问题列出 3–5 种互相竞争的切入方式（不同载体、问题框架、指标），而不是"当前方案的下一步"。
2. **排序**：按"预期信息量 ÷ 成本"排；上限未知的分支，先排"测上限"的 probe。
3. **并行 probe**：每个 probe 有时间与算力上限，产出原始数据和一行结论，不走设计审批。
4. **收敛**：写一页备忘，更新研究地图。
5. **human 剪枝**：在时间盒末尾决定剪掉、继续或提升哪个分支。

### 新问题没有文献时

- **拆成有文献的子问题**：整体问题新，组成部分往往不新。例如"具身 typed decision"可拆成失败恢复何时有收益、typed 概率怎样校准、反事实分支怎样产标签，各有成熟文献。
- **先建测量，再建系统**：先做 GT oracle 上限、信息是否完备、成本量级三项估计；上限接近 0 的分支直接剪掉。
- **借用已知会出现现象的环境**：优先复现已报告该现象的设定，再在上面加自己的变量，而不是从零造载体。
- **存在性证明先于完整验证**：先找最小的、现象会出现的环境，再追求严谨。
- **检索为空也是产出**：写进"已剪掉"或分支证据，作为长期的否定发现。

### 提升到 agent-loop 的条件

同时满足才提升：

- 假设能用一句话写清，成立与不成立指向不同的下一步；
- 有可执行的验收判据（任务指标或已验证的代理）；
- 预计成本高到值得 plan / review / verifier 的门槛。

提升后，研究地图里该分支标为 `promoted`，链接 agent-loop 的 plan；确认结果回填地图。

### 反模式告警

可机械检测、只告警不阻断：

- 同一 Goal 连续 N 个 revision 没有新实验 evidence；
- 同一低成本 task 被 reviewer 判 revise 超过 3 轮；
- 连续 K 个 task 都是"上一个候选的下一步"，期间没有回到根问题比较其他切入方式；
- 研究型 Goal 没有任何分支给出进展信号或上限估计，就开始搭完整系统。

告警的处置是停下来回答"这道门槛和成本相称吗 / 是否该切到探索模式"，而不是继续修订。

### reviewer 在探索模式里审什么

只审三件事：是否列出了竞争性切入方式；排第一的 probe 是否确实信息量最大；证伪条件是否会真的剪掉分支。不审协议细节——协议严谨性留给提升后的确认模式。

## 放在哪里

**先放在本仓，作为独立模式：**

- 新增：一份探索模式 policy、研究地图模板、时间盒预算规则、上述告警；
- 复用：Harness runner（执行 probe 命令与日志）、心跳、memory、pager；
- 不动：Harness 的 READY / VERIFYING / reviewer 准入流程；探索模式的 probe 不经过它。

**拆成独立系统的信号**：需要多个 probe 真正并行编排（多 worker、多节点、自动排队），或需要 co-scientist 式的大规模假设生成与锦标赛排序。这会碰到 [Roadmap](../ROADMAP.md) 的两条边界——Non-goals 里的 "task or hypothesis DAGs" 与 Later 里的 "external driver"；研究地图本身只是文档，不构成 DAG 调度器，但并行编排会。届时需要 human 重新取舍。

## 怎样验证这个提案

1. **回放 roboJev Stage 1.5**：只用 Stage 1.5 开始前已有的信息，按探索模式写研究地图并跑一个周期的 probe 设计。成立条件：第一周期就把"GT oracle 收益上限扫描"或"复用已知会自然失败的环境"列为排前的 probe；对照实际 24 个 revision 的路径。
2. **一个新的真实探索型 Goal**：记录周期数、剪枝数、提升到 agent-loop 的时机，以及 human 在每个时间盒末的决策是否改变了方向。

两项都只是证据，不构成 gate；结果写回本文或 case study。

## 不做

- 不引入自动的大规模假设生成与 Elo 锦标赛；先靠 human 判断力排序。
- 不引入针对 harness 自身的自改进或版本搜索（与 [业界实践](industry-practices.md) 的 RSI 边界一致）。
- 不让探索模式替代 human 对根问题与价值的判断。

## 来源

- [karpathy/autoresearch](https://github.com/karpathy/autoresearch)；本库分析见 [autoresearch](autoresearch.md)
- Novikov et al., [AlphaEvolve: A coding agent for scientific and algorithmic discovery](https://arxiv.org/abs/2506.13131)；Georgiev et al., [Mathematical exploration and discovery at scale](https://arxiv.org/abs/2511.02864)；Google Cloud, [AlphaEvolve：Quantify the optimization target](https://docs.cloud.google.com/gemini/enterprise/docs/alphaevolve/developer-guide/quantify-optimization-target)
- Yamada et al., [The AI Scientist-v2: Workshop-Level Automated Scientific Discovery via Agentic Tree Search](https://arxiv.org/abs/2504.08066)
- Gottweis et al., [Accelerating scientific discovery with Co-Scientist](https://www.nature.com/articles/s41586-026-10644-y)，Nature；[Google DeepMind 博客](https://deepmind.google/blog/co-scientist-a-multi-agent-ai-partner-to-accelerate-research/)
