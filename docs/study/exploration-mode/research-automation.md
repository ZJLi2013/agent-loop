# 研究自动化系统怎样推进开放问题：探索模式的决定表

> 2026-10-12 读取下文列出的一手论文与文档，未运行这些系统。本文是 [探索模式提案](exploration-mode.md) 的调研依据，
> 也是 v0.2 第一个时间盒（TB1）的产出；导航见 [Study 索引](../README.md)。

## 结论

**所有能长时间自主推进的系统都有一个程序化的评估器；没有评估器的系统只产出排序后的假设，验证交给人。**
roboJev 这类问题没有现成评估器，所以探索模式的第一件事不是搜索，而是给每个分支造一个能衡量进展的信号；
AlphaEvolve 的开发指南把这一步写成硬前提，并列出可用的四类构造方法，其中「确定性代理 / 仿真回放」正对应用 GT
做 oracle 上限扫描。

另外三条机制在不同系统里反复出现，直接决定了模板：

- **两级度量**：便宜的筛查驱动搜索，昂贵的验证只给胜出者（AlphaEvolve 的评估级联、DGM 的分阶段评估）。
  这就是探索模式与确认模式的分界。AlphaEvolve 原文把「先用 LLM 审高层想法，再过渡到有机器反馈的实现阶段」
  列为自然的下一步。
- **保留被淘汰的分支**：DGM 的档案保留所有变体作为「垫脚石」，并且偏向选子代少的分支；单点爬山会卡在局部最优
  （autoresearch 的贪心接受规则、DGM 的对照实验）。这正对应 roboJev 一路问「下一个最便宜的候选」的失败方式。
- **人在阶段边界介入，但要先把意图写下来**：co-scientist 把研究目标解析成带评估准则的配置，科学家可以随时改目标、
  注入自己的假设；Agent Laboratory 在每个子任务末设人工检查点，但研究者反映难以把 agent 引到自己设想的方向上。

## 六个问题的答案

| 系统 | 假设空间怎么表示 | 下一个 probe 怎么选 | 何时剪枝 / 停止 | 评估器从哪来 | 人在哪一步 | 预算怎么控 |
|---|---|---|---|---|---|---|
| [AI Scientist-v2](https://arxiv.org/abs/2504.08066) | 实验节点树（计划、代码、指标、反馈、buggy / non-buggy），分四阶段：可行性原型 → 调参 → 研究议程 → 消融 | 非 buggy 节点按 LLM 评估的 best-first；按概率回头修 buggy 节点；记录已试配置避免重复 | 每阶段有显式停止条件（原型跑通、训练稳定、预算用完）；每阶段最佳节点作为下一阶段的根；调试深度 ≤ 3 | 代码产出的指标 + LLM / VLM 评估图表 | 不在环内；人只评最终论文 | 每阶段节点数（21 / 12 / 12 / 12）、单节点 ≤ 1 h、全程 ≤ 15 h |
| [AI co-scientist](https://arxiv.org/abs/2502.18864) | 自然语言假设集合 + 相似度图（去重、聚类）+ 周期性的研究综述 | Elo 锦标赛（两两辩论）排序；进化 agent 只从排名靠前的假设生成新假设，不改原假设 | Supervisor 按汇总统计判断是否到终态 | 无程序化评估器；Elo 被原文称为有限的自动评估指标，验证靠专家评审与体外实验 | 随时改目标、手动评审、贡献自己的假设、指定方向 | 按统计给各 agent 分配资源 |
| [AlphaEvolve](https://arxiv.org/abs/2506.13131) | 程序种群数据库（多指标时用 MAP-Elites 与 Pareto 前沿） | 从种群采样父代，LLM 提出代码变体 | 评估级联：难度递增的测试集，前一级不达标就不进下一级 | 必须是用户提供的程序化评估器；需要人工实验的问题在范围外 | 写评估器与问题描述 | 单次评估约 10 分钟以内；贵的目标用级联 |
| [AlphaEvolve 开发指南](https://docs.cloud.google.com/gemini/enterprise/docs/alphaevolve/developer-guide/quantify-optimization-target) | — | — | — | 单一标量、单调、确定性、由评估代码而非 LLM 或人计算；构造方法：直接计算、性能测试、确定性代理 / 仿真回放、样本外验证；主观目标用专家两两比较拟合打分函数；正确性作硬门槛 | 无法自动打分时问题「尚未准备好」，先造代理 | 便宜方法驱动搜索、昂贵方法确认胜者；3–5 个指标 |
| [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954) | 所有变体的档案（带谱系），保留次优的「垫脚石」 | 父代选择约与得分成正比、与已有子代数成反比；所有变体保留非零概率 | 不删除；分阶段评估（先 10 个任务验证基本能力，通过再扩到 50 个） | 编码 benchmark | 沙箱、监控与可追溯谱系，不参与决策 | 每次执行严格限时；单次完整运行约两周 |
| [Agent Laboratory](https://arxiv.org/abs/2501.04227) | 固定流水线：文献 → 计划 → 实验 → 报告 | 按流水线顺序 | 子任务完成即进入下一步；审稿 agent 打分后决定定稿或回到早期子任务 | LLM 模拟审稿人；原文指出 LLM 自评不如人可靠 | co-pilot 模式在每个子任务末设检查点：继续或附意见重做 | 步数上限；检索加 5 次上限以防死循环 |
| [autoresearch](https://github.com/karpathy/autoresearch)（见本库 [分析](autoresearch.md)） | git 分支即状态，`results.tsv` 活过回滚 | 单点爬山 | 改善就保留、否则 reset；不停，直到人打断 | 约定不修改的评估脚本给出 `val_bpb` | 人维护 `program.md` | 每轮固定 5 分钟 |

## 决定表：映射到探索模式

| 设计决定 | 采用 | 依据 | 不采用 |
|---|---|---|---|
| **进展信号** | 搜索前先有一个信号阶段：写明测量什么、相对什么基线、覆盖哪个子假设；在已知阴性与已知或构造的阳性案例上验证方向并测出成本后才进入搜索；信号带版本号，改动由 human 决定 | AlphaEvolve 指南的四类构造方法、单调与确定性要求、正确性硬门槛，以及「未准备好」判定 | 用 LLM 打分当实时信号（指南明确不建议，co-scientist 与 Agent Laboratory 也承认其局限）；搜索中途悄悄改信号 |
| **状态载体** | 一份研究地图：根问题、收敛条件、分支、probe 记录、已剪掉（带复活条件）、时间盒记录 | co-scientist 的带准则配置与研究综述；DGM 的档案；AI Scientist-v2 记录已试配置；autoresearch 的否定记录活过回滚 | 调度器里的树或种群数据结构（需要自动评估器才有意义） |
| **选下一个 probe** | 按「预期信息量 ÷ 成本」排序，同时偏向 probe 少的分支；上限未知的分支先排测上限的 probe | DGM 的「得分 × 子代少」选择；autoresearch 与 DGM 对照实验显示单点爬山会卡住 | Elo 锦标赛（需要大量假设与 LLM 辩论，先靠人排序） |
| **剪枝与停止** | 分支按证伪条件剪枝但不删除；时间盒有显式停止条件与 probe 数上限；根问题有正、负两个收敛出口 | AI Scientist-v2 的阶段停止条件与节点配额；DGM 不删除档案 | 「不停」（autoresearch 依赖人随时打断） |
| **两级度量与提升** | probe 是便宜筛查；胜出分支按确认模式现有的 plan 格式交接，在那里做重复与严格验证，确认流程本身不改 | AlphaEvolve 的评估级联与「高层想法 → 实现阶段」；DGM 的分阶段评估；AI Scientist-v2 的重复节点 | 在探索模式里做完整协议审查 |
| **human 介入** | 开始时写下根问题、价值与收敛条件；每个时间盒末剪枝 / 继续 / 提升；可随时注入自己的分支 | co-scientist 的目标配置与随时引导；Agent Laboratory 的子任务检查点及其「难以引导」的教训 | 每个 probe 都要人批准 |
| **reviewer** | 时间盒末审框架：竞争切入方式是否列全、排第一的 probe 是否信息量最大、证伪条件能否真的剪枝；把分支拆成假设逐条核对；跨时间盒汇总反复出现的问题 | co-scientist 的深度验证评审与 meta-review | 审协议细节（留给确认模式）；让 reviewer 批准 |
| **预算** | 时间盒声明墙钟、算力与 probe 数；单个 probe 限时；重复动作设上限 | AI Scientist-v2 的单节点限时与全程上限；AlphaEvolve 的单次评估时限；Agent Laboratory 的检索上限 | 无上限运行 |

## 对 roboJev Stage 1.5 的直接含义

- 「按状态选的 oracle 收益」可以用 GT 仿真回放算出，属于指南里的确定性代理，是一个现成的进展信号；1.5-A 从未计算过它。
- 1.5-A 逐个候选推进、每次只问下一个最便宜的候选，是单点爬山；地图应让 probe 少的载体（借用的 VLA 环境、感知执行器）
  与 oracle 扫描并列竞争。

## 来源

- Yamada et al., [The AI Scientist-v2: Workshop-Level Automated Scientific Discovery via Agentic Tree Search](https://arxiv.org/abs/2504.08066)，§3.2、§5、附录 A
- Gottweis et al., [Towards an AI co-scientist](https://arxiv.org/abs/2502.18864)，§3、§5
- Novikov et al., [AlphaEvolve: A coding agent for scientific and algorithmic discovery](https://arxiv.org/abs/2506.13131)，§2.4 与讨论节
- Google Cloud, [AlphaEvolve：Quantify the optimization target](https://docs.cloud.google.com/gemini/enterprise/docs/alphaevolve/developer-guide/quantify-optimization-target)
- Zhang et al., [Darwin Gödel Machine: Open-Ended Evolution of Self-Improving Agents](https://arxiv.org/abs/2505.22954)，§3、§4.2、§5–6
- Schmidgall et al., [Agent Laboratory: Using LLM Agents as Research Assistants](https://arxiv.org/abs/2501.04227)，§3.3.1、§4.2、§5
- [karpathy/autoresearch](https://github.com/karpathy/autoresearch)，经本库 [autoresearch](autoresearch.md) 分析
