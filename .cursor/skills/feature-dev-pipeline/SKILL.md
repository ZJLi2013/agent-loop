---
name: feature-dev-pipeline
description: >-
  通用「大 feature → 子任务 → 设计 → 实现+实验 → 回填 → 下一个子任务」开发流水线的编排者：
  从一个 backlog 文档排优先级、为每个子任务写设计文档、实现并用实验记录驱动调试、把结果回填成
  as-built、再回到 backlog 拆下一个子任务。Use when iteratively developing a large/multi-subtask
  feature with a backlog + per-subtask design doc + experiment record, maintaining a priority todo
  (P0/P1/P2), or when the user says "实现下一个 sub-task / 设计 feature / 拆解 todo / 推进这个大 feature".
---

# Feature Dev Pipeline

把「大 feature → 子任务 → 设计 → 实现+实验 → 回填 → 下一个子任务」的循环固化成可复现流程。本 skill 是**编排者**，具体环节委派给其它 skill，不重复它们的内容。它对仓库、语言、文档目录无任何假设——下文用占位符，首次使用时与 user 约定实际路径并固定下来。

## 文档三件套（pipeline 的 seam）

| 文件（占位符） | 角色 | 谁维护 |
|---|---|---|
| `<backlog>.md`（如 `docs/overall_todo.md`） | 优先级 backlog（P0/P1/P2）+ 现状基线 + 已完成 feature | Phase 1 / Phase 4 |
| `<design-dir>/featureN_<slug>.md` | 单个子任务的设计文档（实现后转 as-built） | Phase 2 / Phase 3 |
| `<exp-dir>/partN-exp.md` | 单个子任务的实验记录（多轮调试可追溯） | Phase 3 |

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
- agent 主动给出推荐排序与理由；**优先级和 scope 由 user 拍板**（这是主要的 human-in-the-loop 点）。
- 输出：backlog 有清晰的下一个子任务 + 现状基线。

### Phase 2 — Design（子任务设计文档）
- 取最高优先级子任务，写 `featureN_<slug>.md`：`核心判断 / Scope（做·不做）/ Problem / Design / 影响范围 / Tests / 边界`。
- 现状代码用 **markdown 文件链接**引用（见下「文档约定」）。
- 若存在多个有显著权衡的方案，列出并让 user 选；否则按 KISS 选最简方案并记录理由。

### Phase 3 — Build + Experiment（实现并实验）
- 实现遵循**最小必要改动**原则：只改达成目标所必需的部分，顺手清理被替换掉的过期逻辑（若项目内有 `minimal-necessary-code` 类 skill 则沿用）。
- 实验记录遵循 `experiment-driven-doc` skill：先写假设/方案/预期到 `partN-exp.md`，长跑前先 smoke，多轮调试用表格追踪，跑完回填结果/分析/结论。
- 远端 / 跨会话 / GPU 长跑遵循 `long-running-agent-harness` skill。
- 这一阶段**多轮调试由 agent 自主完成**（默认选最推荐方案继续，每轮回到文档开头防跑偏，详见 experiment-driven-doc）。
- 拿到结果后：回填 `partN-exp.md`，并把 `featureN_<slug>.md` 从「设计中」转为 **as-built**（状态、端到端验证结论）。

### Phase 4 — Close（回填并拆下一个）
- 更新 backlog：把完成项移入「现状基线/已完成」、刷新可扩展性复盘表、重排剩余优先级。
- 清理实验临时产物（本地 + 远端：一次性脚本、构建/运行日志），保留实验输出与结论。
- 拆解下一个子任务 → 回到 Phase 2。

## 文档约定（项目沉淀）

- **as-built 文档用 markdown 链接引用实现**，例如 ``[`pkg/specs.py` L109-L146](../../pkg/specs.py)``。**不要**用 ```a:b:path 这种聊天专用代码引用语法——它只在 Cursor 对话里渲染成卡片，写进 `.md` 会退化成粘贴的裸代码块。proposed（尚未实现）代码才用普通 ```python 块。
- **实验完结后精简文档**：只留可复现要点（环境/命令/关键参数）+ 核心结果表 + 结论/Next Step，删掉假设推演、预期等设计草稿。
- **不靠改码就判成功**：结论必须有测试/日志/结果/视频或 user 验收支撑。
- **总览表**：每个 `partN-exp.md` 顶部维护一行摘要表（Exp / 目标 / 状态 / 结论）。

## Human-in-the-loop 检查点

默认自主推进；仅在这些点停下等 user：
- Phase 1 的优先级与子任务 scope 拍板。
- Phase 2 有多个显著权衡方案时的选型。
- 破坏性 / 资源敏感操作（删数据、覆盖 checkpoint、强推分支、GPU 长占用）。
- experiment-driven-doc 的硬性中止条件（连续无改善、重复环境错误、Phase 0 假设可能不成立）。

## 组合的其它 skill

- `experiment-driven-doc`：实验文档（假设→设计→执行→结果→分析→结论），Phase 3 的核心。
- `long-running-agent-harness`：通用跨会话 harness / 远端 / GPU / 进度追踪与交接约定。
- 项目内若有「最小必要改动」类 skill（如 `minimal-necessary-code`）：所有代码改动的最小必要原则。
