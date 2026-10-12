# 业界实践与 agent-loop 的能力边界

> 2026-10-12 联网读取下列一手页面与公开 README；未运行这些系统，也不视作完整业界盘点。
> 本文是调研与范围判断，导航见 [Study 索引](README.md)，当前架构见 [design.md](../design.md)。

## 定位

agent-loop 为工作项目提供规划、执行、验证、评审和记忆机制。实验是否有价值、实现是否正确，
由所服务项目的 Goal、数据、指标和验收判据决定。外部信息发现可以由独立 radar 服务多个项目；
其重要性不意味着它必须嵌入 Harness。

当前范围保留既有项目 verifier / reviewer 与 memory 路径。RSI 作为研究参照，不在本轮引入
针对 harness 自身的行为评估集、版本搜索或自动晋升系统；也不接入某个领域 tracker。

## 一手实践对照

| 来源与时间 | 核心机制 | 对当前项目的意义与限制 |
|---|---|---|
| [Anthropic：Effective harnesses for long-running agents](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents)，2025-11-26 | 初始化环境、增量工作、持久化交接、端到端验证 | 与本库 task、交接、verifier 有对应关系；原文主要验证 Web 开发，研究任务的判据仍需项目定义 |
| [Anthropic：Demystifying evals for AI agents](https://www.anthropic.com/engineering/demystifying-evals-for-ai-agents)，2026-01-09 | 区分 task / trial / grader / outcome；组合代码、模型与人工评分；区分能力与回归评估 | 借鉴实际结果与判据的对应关系。所服务项目若开发 agent，可据此建立自己的 eval；普通工程或研究项目使用适合自己的测试与实验指标，无需统一成 agent benchmark |
| [Karpathy：autoresearch](https://github.com/karpathy/autoresearch)，本次读取当前 README | 固定实验时长、val_bpb、保留或丢弃改动；默认 agent 改 `train.py`，人改 `program.md` | 参照有限范围的项目优化循环。固定硬件与预算下才有可比性；详细历史版本分析见 [autoresearch](autoresearch.md) |
| [GEPA](https://github.com/gepa-ai/gepa)，本次读取当前 README；关联论文 [2507.19457](https://arxiv.org/abs/2507.19457) | 从执行反馈提出文本参数变体，经评估与 Pareto 选择优化 prompt、代码或配置 | 是已有可测目标时的优化工具参照；本库当前不引入此搜索流程，也不移用 README 的收益数字作效果承诺 |
| [Sakana：Darwin Gödel Machine](https://sakana.ai/dgm/)，2025-05-30 | 修改 agent 自身代码、用下游编码任务评估、保存候选谱系供继续探索 | 为自改进提供研究例子。特定 benchmark 上的结果不证明通用 RSI 已成熟，也不构成本库增加自改进系统的理由 |
| [LangGraph：Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)，本次读取当前文档 | checkpointer 保存线程状态，store 保存跨线程信息 | 为恢复与长期状态提供参照；持久化、唤醒和任务调度是不同责任，不能仅凭状态落盘就推断已能无人值守恢复 |
| [Hugging Face：Paper Pages](https://huggingface.co/docs/hub/paper-pages)，本次读取当前文档 | 将论文关联到模型、数据集与 demo，并支持讨论 | 说明 radar 可关注成果及相关资产；页面本身不提供本项目所需的变化检测与决策反馈闭环 |

固定发布日期的文章与动态 README 分开标注。后者可能变化；上述内容仅代表读取时看到的机制。
以下组件边界是针对 agent-loop 的设计判断，不是这些来源共同提出的标准架构。

## 已有机制与可借鉴之处

| 问题 | 本库已有路径 | 调研带来的判断 |
|---|---|---|
| 跨上下文继续工作 | active task、交接、plan revision、memory | 继续维护明确的真相源和有界上下文；交接文件与完整宿主会话恢复有不同边界 |
| 判断任务是否完成 | 项目提供 locked verifier，配置 reviewer 时再核对证据解释 | 验证实际结果，研究中的负结果也可以完成任务；判据是否测到 Goal 由项目设计与评审负责 |
| 复用经验 | facts / episodes / lessons 与检索注入 | 先服务后续项目决策；经验积累本身不证明 harness 已自动改进 |
| 观察长任务 | runner budget、心跳、日志与终态 | 进程存在、日志增长、任务有价值是不同问题，见 [心跳](heartbeat.md) |
| 了解外界变化 | 尚无通用持续 radar 组件 | 可在 harness 外独立建设；信息通过正常研究与计划流程被采用 |

## 验证的归属

项目提供“什么算完成或变好”的定义：修复使用回归测试，性能优化使用同条件基线，研究实验
使用假设、对照与证据，信息调研检查来源支持与覆盖。Harness 负责执行锁定的验证并记录证据；
reviewer 审核解释及下一步，不把项目领域标准硬编码进通用 Kernel。

本库软件测试继续验证状态机、guard、adapter 等实现契约。这与另建一套 harness 行为 benchmark
是不同投入，后者当前暂不推进。Anthropic 的 eval 文档在这里是项目验证设计的参考资料。

## Radar：独立的信息发现与变化跟踪

Radar 的价值是持续发现值得关注的变化，并说明来源和适用条件。它可以服务日常领域关注，
也可以围绕某个项目的具体问题工作；没有 active task 时同样有用。

建议的责任边界：

| 组件 | 负责什么 |
|---|---|
| 独立 radar | 维护来源，发现新内容与资产更新，去重、记录版本与时间，筛选与呈现，保存阅读反馈 |
| 工作项目 | 判断信息是否影响 Goal、baseline、假设或阻塞项，决定阅读、实验、暂缓或忽略 |
| agent-loop | 项目采用该信息后，沿既有 plan / review / execute / verify 流程推进 |

关注对象可以包括论文、技术博客、代码 release、模型或数据集发布，以及上游 issue 的关键变化。
内容首发和“现在可以使用了”常是两个不同事件；论文后来开源代码，也可能重新触发关注。

一条有用的信息至少说明：来源与日期、发生了什么变化、证据或资产在哪里。若已知关联项目，
再说明可能影响哪个问题、适用条件是什么。作者声称的收益与项目实测结论应分开保存。

独立 radar 的第一层反馈是阅读与筛选质量。进一步与项目协作时，可按需关联实验结果、暂缓原因
或重新检查条件；“喜欢”“相关”“投入验证”“有实际收益”是不同信号，不能混成一个评分。
这层反馈可以先通过文档链接或人工交接完成，不要求新增 CLI、hook、数据库或自动任务注入。

```text
外部来源 → 独立 radar → 阅读 / 收藏 / 筛选反馈
                         │ 项目决定采用时
                         ▼
                    项目 plan → agent-loop 执行与验证 → 项目结论
                         ▲                              │
                         └──────── 按需关联反馈 ─────────┘
```

持续运行所需的定时触发、抓取游标、失败重试与通知属于 radar 自身的运行设计。将来确实需要
跨系统联动时，再依据真实使用案例定义交接契约。本轮不选定实现项目或领域，也不形成接入计划。

## RSI：保留研究参照，当前使用轻量经验路径

这里的 RSI 指 recursive self-improvement。需要区分三件事：

- 项目优化：agent 改进训练代码、实现或参数，由该项目的指标验证。
- 经验复用：把项目中的事实、否定结论和修复经验写回 memory，供下一轮检索。
- 系统自改进：修改 agent 自己的策略或工具，并验证后续解决问题的能力是否提升。

autoresearch 的默认循环主要属于第一类；本库 memory 支持第二类；DGM 研究第三类，GEPA
则提供可用于多类目标的优化方法。它们的成本与前提不同，不能因为都能“反思”就视作同一种能力。

当前继续用已有 memory、案例记录与人工维护来演进 rules / skills。反复出现的教训可以提示
维护者检查规则，但不在这里新增自动候选搜索、评估晋升或发布流程。项目中的收益与局限留在
项目证据里，通用经验再按已有 owner 边界提炼。
