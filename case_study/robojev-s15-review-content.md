# Case：RoboJEV Stage 1.5，评审一直在审严谨性，没有审被测的内容

> 时间：2026-10-09 至 10-10。执行：Cursor 里的 Claude（agent-loop rules + skills + Harness）；reviewer：WSL Codex
> `gpt-6-astra`，经 Harness 的 plan review 与 task boundary review 调用；human 在 Human Review Gate 批准。
> 远端一个 MI300 节点（RoboSmith + GraspGen + Genesis），本地部署 Decision-1.0-Nox-4B。

## 结论

**Harness 的每一道评审都走了，审的却都是格式与严谨性：判据能否支撑结论、出口是否不同、verifier 有没有漏洞。
没有一道审「这道决策题值不值得问」，也没有一道看过实际发给模型的内容。** 结果是一道只差一个倾角、
答案等于按资产查表的 4 选 1，过了 contract 3 轮评审和 plan r12–r24 共十余轮评审，在 Nox 上跑了 3 轮，
最后由 human 一眼看出：option 设计本身就不对，输入里也没有模型能感知的东西。

具体漏掉的五处：

1. **决策题由工具的现成接口决定**：选了 RoboSmith 已有的选择点（GraspGen 候选按 bucket 排序），没有拿
   Goal 自己的标准（短时程、语义不同、闭环可观测）逐条核对；
2. **reviewer prompt 只覆盖形式**：5 条检查都是设计是否链接、判据与出口、廉价前置、领域先例、只报决定性问题；
3. **关键产物被允许留在代码里**：请求 JSON 的结构与 option 描述被计划明确下放到「dev 上定稿模板」，
   从未作为评审对象；
4. **reviewer 只读文字，不看渲染样例**：「每个状态实际只有 4 种 option、只差接近倾角」这个事实只存在于
   census JSON 里，计划文字里没有；
5. **删门不要求替代**：census 的「oracle − 规则 ≥ 10 pp」门本来已经抓到题目平凡（规则 = oracle），
   验收目标改成「可用」时这道门被删，它覆盖的风险没有交给任何别的检查。

直接代价约 1.5 GPU 小时环境与重放、33 分钟 census、Nox 部署与 3 轮 dev 检查，plan 从 r10 改到 r24，
以及 human 一整天的追问。

## 背景

Stage 1.5 的 Goal：Jev-style 决策模型只读 simulator GT 结构化 state，在代码给出的 options 里选一个，代码执行、
环境判结果，验证闭环可用并沉淀数据。项目 readme 明确要求 option 是「短时程、参数化、可闭环执行」的
下一段技能或恢复动作，语义明显不同，而不是完整动作的几条固定 list。

实际落地的题：RoboSmith 桌面单物体抓取，开局从 GraspGen 候选里选一个完整抓取方案执行到底。

| 实际给模型的 option（bucket） | 出现 / 成功（dev 11 个状态） |
|---|---|
| `top_down_axis_horizontal`（接近近乎竖直） | 8 / 8 |
| `top_down_axis_tilted`（倾斜约 30°） | 11 / 3 |
| `oblique_axis_vertical`（约 60°） | 11 / 0 |
| `side_axis_vertical`（约 85°） | 7 / 0 |

答案几乎就是「选接近倾角最小的那个」；决策时手还没碰到物体，state 里没有任何「发生了什么」。

## 时间线

| 时间 | 事件 | 评审看了什么 |
|---|---|---|
| 10-09 | s15-t1 contract：option = 每个 bucket 取分数最高的候选，≤ 6 个；3 轮评审后 approve | 确定性、预登记、整臂间隙、outcome 分类是否穷尽 |
| 10-09 | r12–r20 plan review | 几乎全在堵 verifier 漏洞：漏记 option、重规划、hash 缺失、场景核对、重放判据 |
| 10-09 夜 | census：规则 10/11 = oracle | ——（这是题目平凡的信号，按当时的门会判 `NO_DECISION_VALUE`） |
| 10-10 上午 | human 把验收改为「可用、接近规则即可」，决策价值门删除 | r21–r22 评审要求补逆序检查（Stage 1 先例），仍是严谨性 |
| 10-10 | s15-t5：Nox 3 轮 dev 检查，Choice 最好 8 / 6（门槛 9），换序后选择改变 7–11/11 | 请求 JSON 与 criteria 文本全在 `jev_dev.py`，无评审；中途查出 bbox 未乘缩放、接触点高度算成 172–283% |
| 10-10 下午 | human：「4 种 option 设计就不好」「输入包含图片吗？否则怎么感知」「关键 json 结构没评审」 | —— |

## 各评审对象实际被审的内容

| 产物 | 有无评审 | 审了 | 没审 |
|---|---|---|---|
| option 定义（contract） | 3 轮，approve | 生成流程是否确定、可复现、可验证 | 选项语义是否不同、只看 state 能否判断、答案是不是一个阈值 |
| 验收判据与 verifier | 每个 revision | 门能否被绕过、两个出口是否不同 | —— |
| 请求 JSON 结构、option 描述文本 | 无 | —— | 字段含义、单位、来源（测量值还是派生量）、渲染出来人能否读懂 |
| 实际 option 列表 / 请求样例 | 无 | —— | 全部 |

## 机制漏洞

### 1. reviewer prompt 只问形式

- `harness/plan_review.py:42–47`：设计是否链接、判据能否支持结论且出口不同、昂贵动作前的廉价前置、
  研究型 task 的领域先例、只报会改变决定的问题。
- `harness/review.py:50–56`（task boundary）：核对结论与证据一致、写下一个 task、选 decision。

两份 prompt 都没有一条问**被测对象本身**：给模型的题、数据、样本是否真的能回答 Goal 的问题。

### 2. 评审对象是文字，不是渲染出来的产物

plan reviewer 按需打开「plan / task 直接引用的证据」，但没有任何规则要求设计附上**渲染样例**——真实的
一份请求、一个状态下的全部 option、一批样本。题目平凡、字段算错这类问题，只看样例才看得出来。

### 3. 关键接口可以下放到代码

`work-planning` 与 `experiment-design` 都没有「影响结论的接口与内容（schema、模板、option 定义）在实现前
冻结为文档、代码按文档实现」这一条。计划写「dev 上定稿模板」就合规地把它移出了评审范围；之后三轮模板
迭代都发生在代码里。

### 4. 问题定义可以由工具决定

没有检查要求「决策点 / 评测题来自 Goal 的标准，而不是所选工具已有的接口」。选 RoboSmith 时的理由是
「候选、IK、执行器现成」——这是环境的优点，却直接变成了题目。

### 5. 删门不要求接替

验收目标被 human 改写时，被删掉的门所防的风险（题目对代码太简单）没有被记录，也没有转交给别的检查。

## 修复

| 漏洞 | 通用修复 | 状态 |
|---|---|---|
| reviewer 只问形式 | plan reviewer 增加一条：审交给被测方的题目 / 数据 / 样本 / 请求能否回答 Goal 的问题（答案是否查表或阈值即得、被测方是否拿得到判断所需信息）；task reviewer 核对实际产物与设计一致、仍在测 Goal，不一致归 `ask_human` | 已接线（t36）；效果未验证 |
| 只审文字 | plan reviewer 要求设计附渲染样例并看样例判断 | 已接线（t36） |
| 领域检查项无处放 | repo 存在 `.agent-loop/review-checklist.md` 时列入两份 reviewer prompt；没有时 reviewer 从 Goal 推出检查条件并在 summary 写明 | 已接线（t36）；各 repo 自写 |
| 接口下放到代码 | `work-planning`：题目、数据、样本、请求及决定它们的 schema / 模板 / 候选定义在实现前写进设计并附样例，改它们等于改设计 | 已实施（t36） |
| 删门无接替 | `work-planning`：删除或放宽一道门时写明它防的风险由哪道检查接替 | 已实施（t36） |
| 工具决定问题 | 由内容审覆盖（题目能否回答 Goal 的问题），不另加条款 | —— |

领域检查项（抓取 option 的语义区分度、GT state 字段来源、Nox 的换序敏感）归项目，不写进通用 skill。
效果验证候选：用一份已知内容有问题的设计与一份合格对照各跑一次 plan reviewer，看是否只对前者点名内容问题。

## 项目侧仍需要

- s15-t6 段边界 contract 里写完整请求 schema（字段、单位、来源）与 2–3 份渲染样例，代码按 schema 渲染，
  verifier 按 schema 检查。
- option 定义附检查表：语义是否不同、是否有结果分化证据、只看 state 人能否判断、是否单一阈值可解、
  决策点是否在执行中有信息增量的边界。

## 证据

均在 `robot_rl_from_zero_to_expert/roboJev`：

- option 列表与 Nox 读数：`exps/stage1_5/exp2_nox-dev-choice.md`（「实际给 Nox 的 option」「结果」）
- 环境与 census：`exps/stage1_5/exp1_robosmith-env.md`、`runs/s15-t4/census.json`
- 原 contract：`exps/stage1_5/feature_grasp-option-choice.md`（「Option 生成与过滤」「GT state schema」）
- 请求实际所在：`script/s15/jev_dev.py`（`describe` / `criterion` / `main`）
- 评审记录：`.agent-loop/reviews/20261009-s15-t1-option-contract*.md`、`.harness/plan-review/*.json`（r12–r24）
