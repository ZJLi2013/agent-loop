# Research / RSI 工作追踪

> 持续更新的跨 feature 追踪。每行写读取日期与读到的层级；表中系统均未运行，数字都是作者报告。
> 导航见 [Study 索引](README.md)；探索模式的设计决定见 [决定表](exploration-mode/research-automation.md)。

## 当前判断

**能稳定涨分的 research agent 都跑在它改不了的评估协议、按服务计费的预算和事后审计之内；
在小开发集上自己挑候选的自改进没有迁移到全集。** RSIGym 的 30 个 Joint run 有 29 个超过初始系统；
同一套服务下 Qwen3.8-27B 同时当研究者和被改进对象，用 6 题开发集选出的 checkpoint 在 37 题全集上
从 56.66% 降到 56.26%。

对 agent-loop 只新增一条要求：**探索模式里，确认胜出分支所用的集合不能是选出它的那个集合。**
两级度量（便宜筛查、昂贵确认）已在决定表里；固定评估、预算上限、持久改动由人批准，都与本库已有边界一致。

## 追踪表

| 工作 | 读取 | 类型 | 改进对象 | 评估器 | 人在哪一步 | 对 agent-loop |
|---|---|---|---|---|---|---|
| [RSIGym](https://github.com/evolvent-ai/RSIGym) | 2026-10-16；README、任务定义、[rsi-index.ai](https://rsi-index.ai/) | 研究环境 + benchmark | 被测系统的训练数据、训练设置、harness，三条 track 按权限切换 | 固定 benchmark 子集，avg@3 官方评测 | 写任务定义与预算；事后审计 | [见下](#rsigym) |
| [ScienceDiscovery](https://github.com/openJiuwen-ai/sciencediscovery) | 2026-10-16；README、开发者文档 | 科研工作台 | 不改模型；Skill Library 经提议 → 授权 → 新版本演进 | 无程序化评估器；Idea Tree 用模型打分 | 首次执行前授权；发布 skill 新版本；暂停 / 恢复 | [见下](#sciencediscovery) |
| [AI Scientist-v2](https://arxiv.org/abs/2504.08066) | 2026-10-12；论文 | 自动科研 | ML 实验代码 | 代码指标 + LLM / VLM 评图 | 只评最终论文 | 阶段停止条件与节点配额进了研究地图模板 |
| [AI co-scientist](https://arxiv.org/abs/2502.18864) | 2026-10-12；论文 | 假设生成 | 假设集合 | 无；Elo 锦标赛 + 专家评审 | 随时改目标、注入假设 | human 随时加分支；不做锦标赛 |
| [AlphaEvolve](https://arxiv.org/abs/2506.13131) | 2026-10-12；论文、开发指南 | 进化搜索 | 程序 | 用户提供的程序化评估器 | 写评估器 | 「信号先于搜索」的主要依据 |
| [Darwin Gödel Machine](https://arxiv.org/abs/2505.22954) | 2026-10-12；论文 | 自改进 | agent 自身代码 | 编码 benchmark | 沙箱与谱系，不参与决策 | 剪枝不删行、偏向 probe 少的分支 |
| [Agent Laboratory](https://arxiv.org/abs/2501.04227) | 2026-10-12；论文 | 自动科研 | 研究流水线产物 | LLM 模拟审稿 | 每个子任务末检查点 | 「难以引导」是 human 在时间盒末介入的反例依据 |
| [autoresearch](https://github.com/karpathy/autoresearch) | 2026-03 @ `228791f`；源码 | 单指标循环 | `train.py` | 约定只读的 `val_bpb` | 维护 `program.md` | 否定记录活过回滚；贪心接受规则是反例。[分析](exploration-mode/autoresearch.md) |
| [GEPA](https://github.com/gepa-ai/gepa) | 2026-10-12；README | 文本参数优化 | prompt、代码、配置 | 用户给定的评估 | 定义目标 | 不引入。[范围判断](industry-practices.md) |

AI Scientist-v2 到 Agent Laboratory 五行的机制细节见 [决定表](exploration-mode/research-automation.md)，这里不重复。

## RSIGym

一个让 research agent 改进另一个系统的环境。agent 在只有 CPU 的容器里工作，训练（Tinker LoRA）、
推理、rollout、评测（Harbor + E2B）、沙箱都通过一把带预算的 key 调用。

**任务由三份文件定义：**

- `instruction.md`：目标、可改与固定的部分、提交物、禁止在评测数据或既有轨迹上训练；还要求设计前先做系统调研。
- `key.json`：`budget_usd: 500`、允许的服务与模型、`train_server.lock` 锁死 base model、dataset 类型、renderer。
- `audit/`：事后审计训练数据重叠、checkpoint 来源与研究行为。

**三条 track：** Data 只改训练数据；Harness 只改执行代码，权重固定；Joint 三者都能改。

**作者报告的结果：**

- 6 个研究 agent × 5 个领域，每次 \$500，起点 Qwen3.5-35B-A3B-Base + minimal harness：
  RSI-Index 0.21–0.48，29/30 提升，4 个研究 agent 各领先至少一个领域。
  RSI-Index = 各 benchmark 的 (final − initial) / (1 − initial) 等权平均。
- Harness track：Opus 5 迭代 DSH，Qwen3.6-35B-A3B-Instruct 权重固定，Terminal-Bench 2.0 从 30.34% 到 40.82%，
  三次全对的任务从 15 到 26。改的是截断输出处理、保留后台服务、结束前自验证。
- 自改进：Qwen3.8-27B 当研究者和被改进对象，6 题开发集选出的 checkpoint 在 37 题全集上 56.66% → 56.26%。
- 作者自述的局限：每个配置只跑一次研究；官方评测复用开发期可见的任务；多轮研究周期的累积增益未评估。

| RSIGym | agent-loop | 判断 |
|---|---|---|
| `key.json` 的权限与锁定字段 | init 时锁定 verifier 与预算的 Harness config | 同构，已有 |
| 按服务计费的统一预算 | runner 的 attempt / wall budget | 本库按机时，不按金额；不改 |
| 设计前要求系统调研 | `experiment-design` 设计前查领域先例 | 已有 |
| run 结束后的审计 | task reviewer 在 task 边界读落盘证据 | 已有，审的时刻不同 |
| 6 题开发集选候选，全集不涨 | 研究地图的提升条件 | **候选**：提升时注明选出胜者的集合，确认用另一组或更大的集合 |
| Harness track 的涨分 | agent-loop 本身就是 harness | 证明自改 harness 在有固定 benchmark 时有效；本库没有这类 benchmark，维持 [不做自改进](industry-practices.md#rsi保留研究参照当前使用轻量经验路径) |

## ScienceDiscovery

本地运行的科研工作台（Apache-2.0）。默认执行器是 JiuwenSwarm；Project、Session、权限、Artifact、provenance
的唯一状态在 Node 控制面，换执行器不移动这些状态。对外能力四项：文献与数据接入、Bubblewrap 沙箱执行、
子 agent 编排、端到端 provenance。

**可对照的机制：**

- **Claim 与证据。** 句子级 claim 用 `[TYPE:ID]` 引用证据；证据链接分 `supports / context / contradicts`。
  只有 PDF 抽取成功后 `fullTextRetrieved` 才为真，这是声称「读过全文」的前提。
- **Reviewer。** 默认关闭；只读，findings 不改 Artifact、不强制重跑、不决定主 run 成败。
- **执行记录。** 每次沙箱执行把代码、stdout、stderr、环境快照存成 SHA-256 内容寻址引用；
  每次模型调用记 Prompt Manifest。没有删除 / GC 接口，也没有自动脱敏。
- **子 agent。** 目标、范围、约束、交付物作为 `run_contract` 注入，不会被上下文摘要掉；
  可要求结果符合 JSON schema，不符即判 failed；子 agent 不能再派子 agent，每个请求最多 50 个。
- **重复调用保护。** 同一工具同一参数第 10 次返回警告，第 20 次硬停，不依赖 prompt。
- **Idea Tree。** 默认 3 轮 × 3 个候选：设计 → 三项独立评估 → 汇总 → 传播。没有检索和代码执行；
  文档明确写分数是模型评估，不能当实验结论。
- **Skill 自演进。** agent 只能提议，必须带理由与来源；用户授权后才发布新版本；发布时对当前 head 重建并检测冲突；
  运行中的 run 冻结 skill 版本；内置库不可被改。

| ScienceDiscovery | agent-loop | 判断 |
|---|---|---|
| claim → evidence，带 `supports / contradicts` | reviewer 只读列出的证据，报告没有 claim 级结构 | **候选**：在一个真实 case 里让 reviewer 逐条结论标出证据与方向，看是否减少 `ask_human` 补证轮；不先改 schema |
| `fullTextRetrieved` 门槛 | 外部调研标注读取层级 | 采用为文档约定（本文「读取」列），零代码 |
| reviewer 只读、不决定成败 | task reviewer 决定 `continue / ask_human / stop` | 不采用，边界决策正是本库 reviewer 的职责，见 [worker / reviewer](planning-review/multi_agent.md) |
| 同参调用 10 / 20 次 | 研究地图「同类重复动作超过 3 次即停」；`when-to-stop` 要求重试换做法 | Policy 层已有；runner 层不加计数，没有复现过的失败 |
| `run_contract` 不被摘要 | plan Goal 与 `task.md` 常驻；首次小窗口 preCompact 只提示换 1M context | 已有 |
| skill 提议 → 授权 → 新版本 | lessons `[x3]` 由人晋升进 rules | 同一边界；版本与冲突由 git 承担 |
| Idea Tree 的模型打分 | 决定表「不用 LLM 打分当实时信号」 | 一致 |

## 待读

- ScienceDiscovery 的 evolution sidecar（PUCT / OpenEvolve）：开发者文档索引有条目，页面 404（2026-10-16）。
- RSIGym 论文正文与公开 run records：看研究 agent 在 \$500 内怎样分配探索与确认，直接对应探索模式的时间盒预算。
- [OpenEvolve](https://github.com/algorithmicsuperintelligence/openevolve)：AlphaEvolve 的开源实现，有程序化评估器时的搜索参照。

## 维护规则

- 一个工作一行进追踪表；机制细节只在本文写一次。某条被 feature 采用后，结论移进该 feature 的文档，这里改成指针。
- 「读取」列写日期与层级：README / 文档 / 论文 / 源码 / 运行过。作者报告的数字与本库实测分开写。
- 新增条目后检查「当前判断」是否改变，不变就不改。
