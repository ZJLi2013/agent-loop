---
name: feature-dev-pipeline
description: >-
  通用「大 feature → 子任务 → 设计 → 实现+实验 → 回填 → 下一个子任务」开发流水线的编排者：
  从一个 backlog 文档排优先级、为每个子任务先定 Goal 再写设计文档、实现并用实验记录驱动调试、把结果
  回填成 as-built、再回到 backlog 拆下一个子任务。强制 Goal-first：feature 文档开头两节固定为「要解决
  什么问题」和「解没解决」，每个实验开跑前先写下它回答 Goal 的哪一问与预期。Use when iteratively
  developing a large/multi-subtask feature with a backlog + per-subtask design doc + experiment record,
  maintaining a priority todo (P0/P1/P2), running a backlog-driven autonomous loop where the agent keeps
  pulling the next task from the backlog without asking each round, defining a feature's goal or scope
  before experimenting, or when the user says "实现下一个 sub-task / 设计 feature / 拆解 todo /
  推进这个大 feature / 从 task.md 取下一个任务 / 按 backlog 一直做下去".
---

# Feature Dev Pipeline

把「大 feature → 子任务 → 设计 → 实现+实验 → 回填 → 下一个子任务」的循环固化成可复现流程。本 skill 是**编排者**，具体环节委派给其它 skill，不重复它们的内容。它对仓库、语言、文档目录无任何假设——下文用占位符，首次使用时与 user 约定实际路径并固定下来。

## pipeline 文档（seam）

| 文件（占位符） | 角色 | 谁维护 |
|---|---|---|
| `<backlog>.md`（如 `docs/overall_todo.md`） | 优先级 backlog（P0/P1/P2）+ 现状基线 + 已完成 feature | Phase 1 / Phase 4 |
| `<design-dir>/featureN_<slug>.md` | 单个子任务的**设计文档 = Goal + 结论 + 定义系统**（开头两节 Goal / 结论，然后数据流 pipeline；实现后转 as-built）。**不是实验总结** | Phase 2 / Phase 3 |
| `<exp-dir>/partN-exp.md` | 单个子任务的实验记录（多轮调试可追溯，**留详细数据**） | Phase 3 |
| `<conclusions-log>`（如项目 `readme.md`/概览文档的「结论速查」区） | **跨 feature 关键结论汇总**（可检索的单一真相来源，**留提炼结论**） | Phase 4 |

> **两层文档分离**：`partN-exp.md` 留详细数据/调试过程（易被埋没）；`<conclusions-log>` 只留"被数据证实、影响后续决策"的提炼结论 + 证据 + 影响 + 指回 partN 的链接。每完成一个 feature 回填一行（见 Phase 4）。首次使用时与 user 约定 `<conclusions-log>` 的位置（无则可省，但推荐有，避免结论散落）。

约定（首次使用时确认）：
- 三个路径前缀（backlog / design-dir / exp-dir）由 user 给定，之后整段开发沿用同一套。
- 编号规则：新 feature = 现有最大编号 +1；`partN-exp.md` 的 N 与该子任务一一对应（不必等于 feature 号，沿用历史序号即可）。
- 在 backlog 的待办项里挂上对应 `featureN` 与 `partN-exp` 链接。
- 若项目暂时只需要其中一两个文档（如纯重构无实验），按需裁剪，但保留「backlog 排序 → 设计 → 回填」主干。

## 四阶段循环

```text
Phase 1 Plan ──► Phase 2 Design ──► Phase 3 Build+Experiment ──► Phase 4 Close ──┐
   ▲                                                                              │
   └──────────────────────────── 拆解下一个子任务 ◄──────────────────────────────┘
```

### Phase 1 — Plan（排优先级）
- 与 user 一起把大 feature 拆成子任务，写进 backlog，按「杠杆高 / 风险低」排 P0/P1/P2。
- agent 主动给出推荐排序与理由；**首次拆解时优先级和 scope 由 user 拍板**（这是主要的 human-in-the-loop 点）。队列排好之后按「持续模式」自主取，不必每轮回来问。
- 输出：backlog 有清晰的下一个子任务 + 现状基线。

### Phase 2 — Design（子任务设计文档）
- 取最高优先级子任务，写 `featureN_<slug>.md`：**开头两节固定为 `Goal` 和 `结论`**，其后 `Design / 影响范围 / Tests / 边界`。
- **`Goal` 只描述要解决什么问题**：一句话，用 user 的语言而不是实现的语言（「把 X 迁到 Y 值不值」，不是「测 KV 复用的曲线」），加必要的现状交代。**不写判据表、不写 scope 清单、不写推演**——那些是流程自嗨，读者不看。
- **`结论` 只回答这个 feature 解没解决它**，附最小证据。
- **写不出 Goal 就不要往下写设计，更不要开跑实验。** 每个子任务都要能指回 Goal；指不回去的就是跑偏。
- **这两节之后再定义系统，不要一上来就贴实验**：用一节「数据流 / Pipeline」把这个 feature 的实际路径串清楚（一句话定义 + 分步表：步骤/做什么/脚本/产物/issue + 关键可视化 checkpoint），让 user 不读实验记录也能看懂系统长什么样、卡点在哪一步。抽象路线图（若有）落到本 feature 的真实脚本与产物上。
- 现状代码用 **markdown 文件链接**引用（见下「文档约定」）。
- 若存在多个有显著权衡的方案，列出并让 user 选；否则按 KISS 选最简方案并记录理由。

### Phase 3 — Build + Experiment（实现并实验）
- **开跑前先声明，但不必等确认。** 每次实验开跑前，在 `partN-exp.md` 里写下它回答 Goal 的哪一问 + 假设与预期（几行即可），然后自己跑。中途冒出新对照臂 / 新变量 / 新工作点也一样——补一条再跑，**不用停下问 user**。这不是审批流程，是给自己留一个可对照的预测：**没有预期，拿到数也判不出是发现还是跑偏**；顺带 user 随时能看出你在测什么。
- **写预期的同时过决策价值门**：结果为否定时 Goal 的答案或 backlog 的优先级会变吗？不会就不跑。**子任务的量级也要配得上 backlog 上的主线瓶颈**——判别方法见 `experiment-driven-doc` 的「决策价值门」。
- 实现遵循**最小必要改动**原则：只改达成目标所必需的部分，顺手清理被替换掉的过期逻辑（若项目内有 `minimal-necessary-code` 类 skill 则沿用）。
- 实验记录遵循 `experiment-driven-doc` skill：先写假设/方案/预期到 `partN-exp.md`，长跑前先 smoke，多轮调试用表格追踪，跑完回填结果/分析/结论。
- 远端 / 跨会话 / GPU 长跑遵循 `long-running-agent-harness` skill。
- 这一阶段**多轮调试由 agent 自主完成**（默认选最推荐方案继续，每轮回到文档开头防跑偏，详见 experiment-driven-doc）。
- 拿到结果后：回填 `partN-exp.md`，并把 `featureN_<slug>.md` 从「设计中」转为 **as-built**——除状态/端到端验证结论外，把实验里**被数据证实、改变了对本 feature 认知**的关键结论**提炼**进 feature 文档（highlight 区），并同步更新开头的 pipeline（哪步通了、卡点移到哪）。feature.md 留提炼结论，`partN-exp.md` 留详细数据/调试过程，两者别互相复制。

### Phase 4 — Close（回填并拆下一个）
- 更新 backlog：把完成项移入「现状基线/已完成」、刷新可扩展性复盘表、重排剩余优先级。
- **回填结论速查**：把本 feature「被数据证实、影响后续决策」的结论，从 `partN-exp.md` 提炼**一行**到 `<conclusions-log>`（结论 + 关键证据 + 对后续的影响 + 指回 partN 链接）；同时标注"待验证/存疑"项。`partN` 留详细数据，`<conclusions-log>` 留可检索结论——避免结论被埋在 partN 里。
- 清理实验临时产物（本地 + 远端：一次性脚本、构建/运行日志），保留实验输出与结论。
- 拆解下一个子任务 → 回到 Phase 2。

## 持续模式：backlog 作为唯一入口

默认按这个模式跑：agent 从 backlog 取一条 → 走完四阶段 → 回填 → 再取下一条，不必每轮问 user。三条约束让它可靠：

**一、backlog 行是索引，不是内容。** 一行 = 一个子任务，只放「事 + 指向 `featureN` / `partN-exp` 的链接 + 状态」。范围、判据、基线选择、边界一律写在 `featureN` 里。自检：**一行需要换行才读得完，就是细节没下沉**——backlog 每轮都被完整读一遍，塞细节等于每轮为过期上下文付一次税。

**二、自主取任务，三种情况才停。** backlog 上已有 P0、且它的 `featureN` 已有 Goal → 直接进 Phase 2/3 不问。只在这三种情况停下等 user：要**新增** backlog 行、要**改优先级**、P0 **清空**了。（这覆盖 Phase 1 「优先级由 user 拍板」那条——那条针对首次拆解，不针对已排好的队列。）

**三、backlog 是任务状态的唯一真相源。** 与 `long-running-agent-harness` 组合时**不要**再建 `.cursor/harness/tasks.json`：backlog 承担它的职责，harness 那边只留 `progress.md` 作为跨 session 的活动笔记与交接。两份任务状态必然漂移。

每轮循环：读 backlog → 取最高优先级未完成项 → 读它的 `featureN`（没有就先写 Goal，见 Phase 2）→ Phase 3 → 回填 `featureN` 与 backlog 的状态列 → 取下一条。

## 文档约定（项目沉淀）

- **as-built 文档用 markdown 链接引用实现**，例如 ``[`pkg/specs.py` L109-L146](../../pkg/specs.py)``。**不要**用 ```a:b:path 这种聊天专用代码引用语法——它只在 Cursor 对话里渲染成卡片，写进 `.md` 会退化成粘贴的裸代码块。proposed（尚未实现）代码才用普通 ```python 块。
- **文档是给人看的，不是给流程看的。** 自检：读前 10 行能否答出「要解决什么问题、解决了没有」？做不到就是 Goal/结论 没写清。**判据表、scope 清单、假设推演、分析过程一律不进 feature.md**，需要就留在 `partN-exp.md`。每加一节先问：读者会因为这节改变行动吗？不会就删。
- **feature.md 是「定义系统」不是「实验总结」**：开头放数据流 pipeline + 提炼后的关键结论（帮 user 快速理解系统与卡点）；详细实验数据/调试过程留在 `partN-exp.md`。若发现 feature.md 正在退化成实验流水账，把过程性内容挪回 partN，只在 feature.md 保留提炼结论。
- **实验完结后精简文档**：只留可复现要点（环境/命令/关键参数）+ 核心结果表 + 结论/Next Step，删掉假设推演、预期等设计草稿。
- **陈述语态**：feature.md / partN 一律写「当前为真的结论」，第三人称，不写「原先以为 X、其实是 Y」这类对文档自己旧措辞的修订说明（git 里有）。语态细则与自检 grep 见 `experiment-driven-doc` 的「文档语态」段。
- **不靠改码就判成功**：结论必须有测试/日志/结果/视频或 user 验收支撑。**验收判据落在 Goal 的语言上**（任务指标 / user 可感知的量），不是「理论上完美一致」；选法见 `experiment-driven-doc` 的「验收判据阶梯」。
- **总览表**：每个 `partN-exp.md` 顶部维护一行摘要表（Exp / 目标 / 状态 / 结论）。

## Human-in-the-loop 检查点

默认自主推进；仅在这些点停下等 user：
- Phase 1 的优先级与子任务 scope、以及 Phase 2 的 Goal——**「要解决什么问题」由 user 定**，agent 不自行替 user 定义。队列已排好时的例外见「持续模式」第二条。
- Phase 2 有多个显著权衡方案时的选型。
- 破坏性 / 资源敏感操作（删数据、覆盖 checkpoint、强推分支、GPU 长占用）。
- experiment-driven-doc 的硬性中止条件（连续无改善、重复环境错误、Phase 0 假设可能不成立、连续 2 轮结果不改变主线决策）。

## 组合的其它 skill

- `experiment-driven-doc`：实验文档（假设→设计→执行→结果→分析→结论），Phase 3 的核心。
- `long-running-agent-harness`：通用跨会话 harness / 远端 / GPU / 进度追踪与交接约定。
- 项目内若有「最小必要改动」类 skill（如 `minimal-necessary-code`）：所有代码改动的最小必要原则。
