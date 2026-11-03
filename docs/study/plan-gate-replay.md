# Gate 只摆设计与结论：回放

> [Study 索引](README.md) · 被测措辞是 `work-planning` 的 plan 模板、第 1 步的样例位置与第 5 步的 Gate 问题，对应
> [#154](https://github.com/ZJLi2013/agent-loop/issues/154)。回放于 2026-11-03，改动前的对照基于 `eed794e`。

## 结论

模板与 Gate 的格式改动留下：改动后 4 份 plan 草稿都是 Goal → 设计 → 当前结论 → 分隔线，执行细节与 Experiment Log 在分隔线以下；
4 份 Gate 问题都先给设计与当前结论、再给逐 task 意见，不含 task 步骤。改动前 4 份都没有「设计」一节，也没有分隔线。

「判断类任务（分类、排序、判关系）默认交给读全上下文的 agent」这一句不加：改动前 planner 已经这样做。

| 场景 | 请求 | 改动前 | 改动后 |
|---|---|---|---|
| J1 正例 | 从 3000 篇论文库还原一条工作线，每篇判它在解决哪篇前作的什么问题 | 2/2 交给读原文的 agent，引用句只定位候选 | 2/2 |
| J2 对照 | 按已由上游定好的 `subfield`、`published` 两列统计近 12 个月论文数 | 2/2 脚本计数，不重新分类 | 2/2 |

推翻条件：同类判断类场景改动前正例 0/2（设计用「逐条贴标签 → 计数 → 截阈值」而不说明为什么不会静默漏掉）。
#154 的原始案例里规则管线是在已有关键词计数代码与全库规模下长出来的；这个夹具从零写新 Goal，没有复现那个起点。

## 公开做法对照

公开做法支持这两个取舍，没有与之冲突的；#154 原始案例那种「已有规则代码上长出管线」的起点，三份都没有覆盖。

| 公开来源与位置 | 输入起点与方法 | 与本仓库取舍的对应 | 对交付的影响 |
|---|---|---|---|
| OpenAI，[A practical guide to building agents](https://cdn.openai.com/business-guides-and-resources/a-practical-guide-to-building-agents.pdf)，「When should you build an agent?」 | 给构建者选场景：细腻判断、难维护的规则集、依赖非结构化数据时用 agent，否则确定性方案就够 | 与 base planner 的分法一致：J1 读全文判关系交给 agent，J2 计数写脚本。「难维护的规则集」最接近 #154 的起点，但它是选场景的标准，不是规划时的默认 | 判断类一句仍不加 |
| Anthropic，[Building effective agents](https://www.anthropic.com/engineering/building-effective-agents)，「When (and when not) to use agents」与 Summary | 先用最简方案，只在可证明改善结果时加复杂度；定义清楚的任务用 workflow，需要模型决策时用 agent | 同上；「只在可证明改善时加」也对应本次出口：改动前已成立的措辞不加。它要求「显式展示 agent 的规划步骤」，指的是让用户能看到这些步骤；本次的步骤仍在 plan 分隔线以下，只是不进 Gate 问题 | 不改 |
| Malte Ubl，[Design Docs at Google](https://www.industrialempathy.com/posts/design-docs-at-google/)，「Anatomy of a design doc」与「When not to write a design doc」 | 设计文档给评审看取舍：目标与非目标、设计、备选方案；只写「我们要这样实现」的文档是实现手册，不值得评审 | 「设计」一节的关键选择各写替换了什么，对应备选方案；「不做」对应非目标；执行步骤放在分隔线以下，正是不让实现手册占据审阅面 | 模板改动保留 |

## 输入

合成项目 paperline：3D 视觉论文库，3000 篇，每篇有元数据、参考文献、引用句与全文；`docs/papers.csv` 的两列由上游人工分类定好。
planner 路径是一次调用，只给 `work-planning` 与项目文件，请求是写出新 Goal 的 plan 草稿、主线改动与准备在 Gate 上问 human 的问题。
每格 2 次，模型为 Codex CLI 上的 gpt-6-astra（reasoning effort high），8 次调用全部有效。

## 判定

- J1：设计把「判前作关系」交给读全文的 agent 算命中；用规则管线时要同时写明信号形式与为什么不会静默漏掉才算命中。
- J2：脚本计数算符合，把计数交给 agent 逐篇判算误触发。
- 格式：章节顺序按标题位置自动核对；Gate 问题由 agent 逐份人工读，判它是否先给设计与结论、是否含 task 步骤。

## 解释边界

- 每格 2 次、一个模型、一个夹具；格式只看改动后，不作撤措辞依据。
- 改动前的 J1 已带 #153 的「先用上」措辞，两次都先做两篇论文的手工切片；规模化之后会不会长出规则管线，这里没有测到。
- 公开对照只取三份构建指南与文档实践，它们是观点，不是本仓库的行为读数。
