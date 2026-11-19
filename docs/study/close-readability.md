# 入口文档的逻辑可读性（#237）

**实验线的入口文档要让 human 只读它就能说出：做了哪几步、每步产出什么、数据从哪来到哪去、训练与评估各用多少什么数据。** 现行 CLOSE self-audit 与 task reviewer 只查多余、不查缺失，会放行内容齐全却串不起来的入口。本页记录入口要满足的约束、支撑它的证据与评测方法的选择；把约束写进 `experiment-design` 与 `task_review.md` 的改动另由 [#237](https://github.com/ZJLi2013/agent-loop/issues/237) 的 PR 落地。

## 入口文档的约束

适用于 task CLOSE 写入或改动的项目实验记录的入口（实验线 readme 或 plan 链接的结论页）：

1. **步骤**：一张表列出每一步的输入、产出与交给谁；表前一句话说明步与步怎么衔接。几件事前后衔接时分开写，不并进一张漏斗表。
2. **数据清单**：训练与评估各一张，每个来源一行（数量、作用）；**清单上方先给每个用途的合计条数**，未定的写「未定」，不留空。
3. **术语**：在第一次使用之前定义，一条一句。
4. **说明只写一次**：表头已说清的，表下不逐行复述。
5. **不写待 human 选的做法与 task 状态**：它们归 `task.md` 与结构化提问，入口只留一句结论或指针。

self-audit 删减时，解释流程与数据流的骨架不按「删了不改变下一条命令」删除。

## 证据

来自一个机器人 world-model 实验项目的一条数采与 post-train 实验线，入口文档前后三版。

| 版本 | 情况 | 结果 |
|---|---|---|
| 原版（几个 task 均过 CLOSE self-audit 与 task review） | 步骤只以 ①②③ 标签出现在一张漏斗表末列；训练侧组成写了，但分散在一张表与三条条目；两个关键术语无定义 | human 读不出数采是两件事、找不到训练集怎么构成；现行 task reviewer 在这一版上回放 2/2 选 `continue`，未提可读性 |
| 按约束 1–4（不含合计与只写一次）重写 | 新增步骤表、训练 / 评估清单、术语表 | human：仍答不出「实际提供了多少条训练数据」，清单下的逐行说明「太绕」；另指出待选做法表应在 `task.md` |
| 按 human 反馈再改 | 清单上方给出训练侧合计与混入旧数据后的合计，删去重复说明，待选做法移出 | 本页约束 2、4、5 由这一轮反馈得出 |

原版的三处问题都不是「内容没写」，而是只读入口串不起来；所以约束写成入口的结构要求，不写成「必须包含某项内容」。

## 评测方法的选择

| 参照 | 做法 | 对本库的取舍 |
|---|---|---|
| [Teach-back](https://www.ahrq.gov/health-literacy/improve/precautions/tool5.html)（AHRQ Health Literacy Universal Precautions Toolkit，Tool 5） | 讲解者请对方用自己的话复述，复述不出就说明讲解没讲清，改讲法而不是怪听者 | reviewer 只读入口复述四项，复述不出算入口的缺口；不从 plan 或 Experiment Log 补全 |
| [Diátaxis](https://diataxis.fr/) | 文档按读者任务分为 tutorial、how-to、reference、explanation，不混写 | 入口承担 explanation（步骤与数据流），读数与配方是 reference，留在链接的文档 |
| [Zheng 等，2023，Judging LLM-as-a-Judge](https://arxiv.org/abs/2306.05685) | LLM 评审有位置、冗长与自我偏好等偏差，需要与人工判断对照 | 正反例取自 human 实际读过的版本，预期以 human 原话为准；判分不靠关键词匹配 |
