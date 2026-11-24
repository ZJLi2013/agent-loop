---
name: project-docs
description: >-
  项目文档的分工与组织：项目 readme、task.md、feature 与 exp、分组 readme、讨论稿各写什么、放哪；
  研究问题怎么划分成 feature，共用设计放哪，脉络与 Experiment Log 怎么写，冻结后留什么。
  Use when writing or editing a project readme, features/, exps/, a group readme or a task design section,
  or when deciding how to split a research question into features.
---

# Project Docs

本 skill 只管项目文档的分工与组织。何时写、谁批准归 `work-planning`，语态与首屏标准归 `write-for-humans`，`task.md` 的格子归 `task-state`，实验的假设与判据归 `experiment-design`。

## feature 与 exp 两份文档

每个具体 feature 只有两份工作文档：`features/<feature>.md` 写设计，`exps/<feature>.md` 写实验，同路径一一对应并被 git 跟踪；`<feature>` 可以带子目录（`features/<组>/<名>.md` 对应 `exps/<组>/<名>.md`），两侧逐级镜像。`features/` 与 `exps/` 是同一目录下的一对，可以在项目根，也可以在项目内任一子目录：项目下的每个子目录是一个独立实验组时（如 `<组>/features/` 对应 `<组>/exps/`），各组各有一对；本文的 `features/`、`exps/` 都指这一对。把现有文档改到本规范时保留项目的目录嵌套：`features/` 建在现有 `exps/` 的同级，现有文件与目录不移动、不删除、不重命名，只新增或改写与 exp 一一对应的 feature 文档。一个 feature 是一处能单独设计、单独验收的改动，或一个研究问题下的一组实验；一个 Goal 有一到多个 feature。Goal 只写在 `task.md`：主线行的问题与退出条件，加 `## Goal（…）` 一段；主线行的 plan 格链接这个 Goal 的全部 feature。Harness 的 plan document（`plan_doc`）就是 feature 文档，下文的 plan 都指它。Goal、feature 与 task id 用说明内容的短语义名（kebab-case，如 `scene-runtime-refactor`），不用 `s2`、`t3` 这类序号；序号只留给 `rN` revision。

一个项目的文档只有下面几类，各写各的，不互相复制。「不写什么」里能按位置或字面判定的由 Harness 拒绝；其余按本表由写的人守，task reviewer 只审内容，不审格式与分工：

| 文档 | 位置 | 写什么 | 不写什么 | 执行点 |
|---|---|---|---|---|
| 项目入口 readme | 项目根 `readme.md` | 长线方向、当前 Goal 一句；每个 feature 或分组一行：一句当前事实（可带关键数）加 feature 与 exp 的链接，不套第二层纯链接 readme | 进展、revision、task 清单与状态、设计 | CLOSE lint 拒绝本 task 写的纯链接索引行 |
| `task.md` | `.agent-loop/task.md`，每项目一份 | 主线（Goal 的问题、退出条件与它的 feature 链接）、task 行（id、问题、两个去向、状态，行序即优先级，链到 feature 里的设计节）、候选 | 设计、`rN`、失败计数、预算、读数、结论、模板外的列与章节 | Harness 解析 task 行；CLOSE lint 拒绝列数与模板不一致的新增行 |
| feature 文档 | `features/<feature>.md`，每个具体 feature 一份 | 设计与关键结论：首屏字段 `目标`、`现状`、`下一步`（研究型另加 `原因`、`已排除`），写法见 `write-for-humans`「给 human 读的项目文档」；所属 Goal 与本 feature 要让什么成真、设计、当前结论（项目结论的唯一定义处，每条一句判断带关键数，链到 exp 里支撑它的一节）、脉络；每个 task 的设计是其中以 task id 开头的一节，含绑定 revision 的 `- rev：rN` 一行，CLOSE 时删除 | Goal 的定义（归 `task.md`）、逐 run 表、原始读数、复现命令、日志与输出摘录、Experiment Log、要 human 选的项 | `init` 拒绝不在 `features/` 下的新 `plan_doc`，以及指向别处（exp、另一个 feature、`.harness/`）的 task 设计链接；CLOSE lint 拒绝缺首屏字段与 `## Experiment Log`；task reviewer 在 CLOSE 只读首屏答三问 |
| exp 文档 | `exps/<feature>.md`，与 feature 同路径 | 实验细节与数据：每个实验一节，写配置与输入（数据、seed、环境、参数）、读数表、复现命令与产物位置；Experiment Log | 设计（干预、判据、预算）、结论、首屏字段、`- rev：rN`、以 task id 开头的标题、Experiment Log 外以 task id 为行的表、要 human 选的项 | CLOSE lint 拒绝 `Goal`、`设计`、`当前结论`、`结论`、`脉络` 标题、首屏字段行、`- rev：` 行，没有同路径 feature 与未跟踪文件，以及本 task 新增的设计态行 |
| 分组 readme（可选） | `features/<组>/readme.md` 与 `exps/<组>/readme.md`，成对 | features 侧是系列入口：首屏字段同 feature 文档；组内每个 feature 一行：一句当前事实加链接；之后是组内拆开的 feature 共用的问题与设计（被测对象、门、数据基准）；脉络。exps 侧只留实验 id 对照、共用的配置与数据入口 | 单个 feature 的设计、task 设计段、结论的展开（归各 feature）；exps 侧另不写首屏字段与结论 | features 侧按 feature 文档查首屏字段与 Experiment Log、按 readme 查纯链接索引行；exps 侧按 exp 文档查，并要有同路径的 features 侧 readme；`init` 不接受它作 `plan_doc` |
| 讨论稿（可选） | `discussions/<YYYY-MM-DD>-<议题短名>.md`，一个议题一份 | 两个 agent 就一个未定实验的讨论，写法见 `work-planning`「讨论」 | 收敛后的设计（归 feature）、读数表（归 exp） | 不放 `features/` 与 `exps/`；由 feature 脉络链接 |

task 设计不另起文档，task 行只链到它所在的那一节。feature 下的子步骤与子实验是它的 task 设计段与 exp 里的一节。研究问题按它要交付或判定的东西定，不含做法：换干预、起点或数据是同一问题下的新实验。开新的 feature 与同名 exp 只有两种情况：能单独设计、单独验收的另一处改动或另一个研究问题；同一问题下，现有 feature 分隔线以上（含标题、表格与空行）再加一个实验就会超过约 80 行时，下一个实验放进同一分组目录下的新 feature，已有实验不搬。共用的部分（问题、被测对象、门、数据基准）单份时写在设计节开头，拆开后移到覆盖全部使用者的最近一层分组 readme，只写一次，各 feature 链过去并只写差异；已被做完的实验引用的共用定义不改语义，之后的变化写进使用它的 feature 的差异。做完的实验 feature 冻结，`下一步` 链到后继。按内容类型分工，同一种内容只归一份文档：设计与结论在 feature（拆开的 feature 共用的设计在分组 readme），结论只在「当前结论」定义一次，项目 readme 只放一句并链过去；配置、读数、复现与逐 run 记录在 exp，feature 只链过去；进展与状态只在 `task.md`。待 human 选的做法走结构化提问（`when-to-stop`），不进任何文档。task 关闭时 Harness 删掉它的设计段，不留 archive；要留下的结论写进 feature 的当前结论，理解结论仍必需的设计写进设计节，支撑数据写进 exp。在途 Goal 的旧位置 plan（`features/` 之外）只在它已有 task 归档后才被 `init` 接受，做完冻结；新 Goal 一律用 `features/`。

```markdown
# <feature 名称>

Plan Revision: 1
Plan Review: proposed

- **目标**：<一句白话>
- **现状**：<一句，带关键数>
- **下一步**：<一句>

## Goal
<所属 Goal（链到 `task.md` 主线行），本 feature 回答的问题及首屏没写的边界，不复述首屏目标；产出给人读或给下游用时写明读者>

## 设计
<当前选定的实验或 probe 方案：一句话策略；手写的最终产出样例（不是结果）；2–4 个关键选择，各写替换了什么；不做什么；
验收怎么判、不靠 human 的领域判断。结合当前 task 的设计段，执行者不用再决定被测假设、干预、输入、判据与预算，
就能定下第一个执行动作和结果对应的下一步。机制有多步时附一张示意图。
做完的实验在本节留下理解当前结论仍必需的设计：问题、关键干预、判据、适用条件与 exp 链接；系列共用的部分
（被测对象、门、数据基准）只写一次：单份时在本节开头，拆开后在分组 readme；某个实验与它不同时写明差异>

## 当前结论
<现在为真的判断，每条一句带关键数、对应它证实或推翻的设计要素，并链到 exp 里支撑它的一节；设计中就明确写未验证>

## 适用边界
<当前结论成立的条件与不覆盖的范围，每条一句>

## 脉络

| 阶段 | 问了什么 | 结论 | 带来的改变 |
|---|---|---|---|
<一个阶段一行：回答同一个问题的一段 task，或一次 Plan Revision / Goal 变更；「带来的改变」写改变的下一条命令，
或旧 Goal → 新 Goal 及原因；格子里不写读数与链接>

---
以下是执行细节，human 不用读。

## 系统 / Pipeline
（确实存在系统路径时才写）

## <task id> <标题>
<task 设计>
```

`exps/<feature>.md`：

```markdown
# <feature 名称> 的实验细节

## <一个实验>
<配置与输入（数据、seed、环境、参数）、读数表、复现命令与产物位置>

## Experiment Log
<单次实验的假设、判据、结果与证据>
```

「脉络」是阶段之间、Plan Revision 之间因果的唯一归属，下一步动作就是最后一行的「带来的改变」。task 边界上把本 task 并入当前阶段行（task 范围与结论）；下一条命令换方向（新问题、假设被推翻而要换做法、replan、human 纠偏、stop）时才开新行。plan review 与批准不单独占行，除非改变了方向。逐 task 的读数与链接写进 exp 的 Experiment Log。谁做决定谁当场写：task 边界由 reviewer 写（未配置时由 worker），Goal Review 与 human 纠偏由执行 RECONCILE 的agent 写 human 的决定。已结束的阶段行只追加更正行，不改写；CLOSE、replan 与 Goal 冻结都不删它。旧的逐 task 行在脉络里合并成阶段行，不算改写。

单次实验追加到 exp 的 Experiment Log。同一 feature 下的多个独立实验是 feature 里的多个 task 设计段、exp 里的多个实验节；结论只写进 feature「当前结论」，每条链到 exp 里支撑它的实验节。

## 冻结

feature 冻结为 as-built 时只留首屏、Goal、设计、当前结论、适用边界与脉络，首屏 `下一步` 写「已冻结」加后继 feature 的链接，没有后继写「无后继」；exp 文档留实验节与 Experiment Log，两份都不删、不搬。冻结的时机归 `work-planning`。
