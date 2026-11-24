---
name: work-planning
description: >-
  把 Goal 落成一份 feature 文档与同名 exp 文档、最近 1–2 个渐进 task 与 Human Review Gate；
  处理 Plan Revision、Goal Review 和人工纠偏后的 RECONCILE。
  Use for new goals, proposed plans, plan review, goal refresh, or user corrections.
---

# Work Planning

本 skill 是 planning Policy。状态转移归 `harness/protocol.py`，task schema 归 `task-state`，
实验假设与判据归 `experiment-design`。

## feature 与 exp 两份文档

每个具体 feature 只有两份工作文档：`features/<feature>.md` 写设计，`exps/<feature>.md` 写实验，同路径一一对应并被 git 跟踪；
`<feature>` 可以带子目录（`features/<组>/<名>.md` 对应 `exps/<组>/<名>.md`），两侧逐级镜像。一个 feature 是一处能单独设计、单独验收的改动，或一个研究问题下的一组实验；一个 Goal 有一到多个 feature。Goal 只写在 `task.md`：
主线行的问题与退出条件，加 `## Goal（…）` 一段；主线行的 plan 格链接这个 Goal 的全部 feature。Harness 的 plan document（`plan_doc`）
就是 feature 文档，下文的 plan 都指它。Goal、feature 与 task id 用说明内容的短语义名
（kebab-case，如 `scene-runtime-refactor`），不用 `s2`、`t3` 这类序号；序号只留给 `rN` revision。

一个项目的文档只有下面几类，各写各的，不互相复制。「不写什么」里能按位置或字面判定的由 Harness 拒绝；
其余按本表由写的人守，task reviewer 只审内容，不审格式与分工：

| 文档 | 位置 | 写什么 | 不写什么 | 执行点 |
|---|---|---|---|---|
| 项目入口 readme | 项目根 `readme.md` | 长线方向、当前 Goal 一句；每个 feature 或分组一行：一句当前事实（可带关键数）加 feature 与 exp 的链接，不套第二层纯链接 readme | 进展、revision、task 清单与状态、设计 | CLOSE lint 拒绝本 task 写的纯链接索引行 |
| `task.md` | `.agent-loop/task.md`，每项目一份 | 主线（Goal 的问题、退出条件与它的 feature 链接）、task 行（id、问题、两个去向、状态，行序即优先级，链到 feature 里的设计节）、候选 | 设计、`rN`、失败计数、预算、读数、结论、模板外的列与章节 | Harness 解析 task 行；CLOSE lint 拒绝列数与模板不一致的新增行 |
| feature 文档 | `features/<feature>.md`，每个具体 feature 一份 | 设计与关键结论：首屏字段 `目标`、`现状`、`下一步`（研究型另加 `原因`、`已排除`），写法见 `write-for-humans`「给 human 读的项目文档」；所属 Goal 与本 feature 要让什么成真、设计、当前结论（项目结论的唯一定义处，每条一句判断带关键数，链到 exp 里支撑它的一节）、脉络；每个 task 的设计是其中以 task id 开头的一节，含绑定 revision 的 `- rev：rN` 一行，CLOSE 时删除 | Goal 的定义（归 `task.md`）、逐 run 表、原始读数、复现命令、日志与输出摘录、Experiment Log、要 human 选的项 | `init` 拒绝不在 `features/` 下的新 `plan_doc`，以及指向别处（exp、另一个 feature、`.harness/`）的 task 设计链接；CLOSE lint 拒绝缺首屏字段与 `## Experiment Log`；task reviewer 在 CLOSE 只读首屏答三问 |
| exp 文档 | `exps/<feature>.md`，与 feature 同路径 | 实验细节与数据：每个实验一节，写配置与输入（数据、seed、环境、参数）、读数表、复现命令与产物位置；Experiment Log | 设计（干预、判据、预算）、结论、首屏字段、`- rev：rN`、以 task id 开头的标题、Experiment Log 外以 task id 为行的表、要 human 选的项 | CLOSE lint 拒绝 `Goal`、`设计`、`当前结论`、`结论`、`脉络` 标题、首屏字段行、`- rev：` 行，没有同路径 feature 与未跟踪文件，以及本 task 新增的设计态行 |
| 分组 readme（可选） | `features/<组>/readme.md` 与 `exps/<组>/readme.md`，成对 | features 侧是系列入口：首屏字段同 feature 文档；组内每个 feature 一行：一句当前事实加链接；之后是组内拆开的 feature 共用的问题与设计（被测对象、门、数据基准）；脉络。exps 侧只留实验 id 对照、共用的配置与数据入口 | 单个 feature 的设计、task 设计段、结论的展开（归各 feature）；exps 侧另不写首屏字段与结论 | features 侧按 feature 文档查首屏字段与 Experiment Log、按 readme 查纯链接索引行；exps 侧按 exp 文档查，并要有同路径的 features 侧 readme；`init` 不接受它作 `plan_doc` |
| 讨论稿（可选） | `.agent-loop/discussions/<YYYY-MM-DD>-<议题短名>.md`，一个议题一份 | human 开的多方讨论：头块、当前共识、菜单、讨论记录，写法见「讨论」 | 生效的结论与设计（归 feature）、读数表（归 exp） | 不放 `features/` 与 `exps/`；收尾时删除 |

task 设计不另起文档，task 行只链到它所在的那一节。feature 下的子步骤与子实验是它的 task 设计段与 exp 里的一节。
研究问题按它要交付或判定的东西定，不含做法：换干预、起点或数据是同一问题下的新实验。开新的 feature 与同名 exp 只有两种情况：
能单独设计、单独验收的另一处改动或另一个研究问题；同一问题下，现有 feature 分隔线以上（含标题、表格与空行）再加一个实验
就会超过约 80 行时，下一个实验放进同一分组目录下的新 feature，已有实验不搬。共用的部分（问题、被测对象、门、数据基准）
单份时写在设计节开头，拆开后移到覆盖全部使用者的最近一层分组 readme，只写一次，各 feature 链过去并只写差异；
已被做完的实验引用的共用定义不改语义，之后的变化写进使用它的 feature 的差异。做完的实验 feature 冻结，`下一步` 链到后继。
按内容类型分工，同一种内容只归一份文档：设计与结论在 feature（拆开的 feature 共用的设计在分组 readme），结论只在「当前结论」定义一次，项目 readme 只放一句并链过去；配置、读数、复现与逐 run 记录在 exp，feature 只链过去；进展与状态只在 `task.md`。
待 human 选的做法走结构化提问（`when-to-stop`），不进任何文档；human 开的讨论的菜单只在它的讨论稿里，见「讨论」。
task 关闭时 Harness 删掉它的设计段，不留 archive；要留下的结论写进 feature 的当前结论，理解结论仍必需的设计写进设计节，支撑数据写进 exp。
在途 Goal 的旧位置 plan（`features/` 之外）只在它已有 task 归档后才被 `init` 接受，做完冻结；新 Goal 一律用 `features/`。

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

「脉络」是阶段之间、Plan Revision 之间因果的唯一归属，下一步动作就是最后一行的「带来的改变」。
task 边界上把本 task 并入当前阶段行（task 范围与结论）；下一条命令换方向（新问题、假设被推翻而要换做法、replan、
human 纠偏、stop）时才开新行。plan review 与批准不单独占行，除非改变了方向。逐 task 的读数与链接写进 exp 的 Experiment Log。
谁做决定谁当场写：task 边界由 reviewer 写（未配置时由 worker），Goal Review 与 human 纠偏由执行 RECONCILE 的
agent 写 human 的决定。已结束的阶段行只追加更正行，不改写；CLOSE、replan 与 Goal 冻结都不删它。旧的逐 task 行
在脉络里合并成阶段行，不算改写。

单次实验追加到 exp 的 Experiment Log。同一 feature 下的多个独立实验是 feature 里的多个 task 设计段、exp 里的多个实验节；
结论只写进 feature「当前结论」，每条链到 exp 里支撑它的实验节。

## 讨论

human 带来一个还没收窄的议题、要几方来回讨论时开；产出是至多 5 条菜单，由 human 选。它不是裁决：agent 自己要定的事
照 `when-to-stop` 一轮裁决，agent 不自己发起多轮讨论，只能在推荐里建议「就 X 开一次讨论」。

- **开**：只由 human 开：说「brainstorm / 讨论 <议题>」，或带来 idea 要求讨论。议题照录原话，加服务的决定（human 读完要定什么）
  与资源约束。
- **各方**：局外是项目的 reviewer 命令（未配置时同 `when-to-stop` 的默认 reviewer），在独立上下文里先起草，只给议题、
  服务的决定与约束、human 已定的 Goal、可定位的事实（exp 读数、feature 的当前结论），不给 agent 的路线推荐；交给它的完整请求
  附在讨论稿文末。局内是项目会话的 agent，带全部上下文回应。human 随时加入，由局内整理成条目；human 说定了的按已定处理。
- **讨论稿**：头块写议题原话、服务的决定、各方、输入版本（commit 或时间戳）、状态（进行中 / 收敛 / 截止）；正文是当前共识，
  首屏按 `write-for-humans`；讨论记录放文末 `## 讨论记录`。
- **回应**：每次一节 `### R<n> 局外|局内|human <模型>`，由带 ID 的条目组成（D1、D2…，首次分配，之后只引 ID）。每条写立场
  （新提 / 同意 / 反对 / 收窄 Dx）、主张、依据、改变哪个下一步动作、处置（已改正文 / 不改及理由 / 待核查）；只改措辞的直接改正文。
  反对写出什么结果能定这个分歧。共识不是证据：事实问题写成待核查，不靠讨论标成成立。
- **上限**：局外起草一次，之后局外、局内各至多 3 次回应，重新起草计入回应次数，human 的不计。讨论不跑实验、不占机时，待核查的条目进菜单作 probe。
  双方回应过同一版正文、每条影响动作的异议都有双方认的处置即收敛；次数用完记截止，分歧照留。
- **收尾**：菜单每条写候选、改变哪个下一步动作、第一步与成本、来源，用结构化提问交 human，问题脱离讨论稿也能读懂。
  human 选中的条目进 Goal 或现有 feature：新 Goal 从下一节第 1 步起，改已有 Goal 或 scope 走 Human correction，脉络追加一行写
  讨论的问题与选择；没选中、仍可能做的进 `task.md` 候选。选择与去向落盘后删除讨论稿，不回写、不归档；
  落盘前（含收敛或截止后等 human 选）不删，未收尾的讨论稿路径写进 `progress.md` 的最新交接段。
- **项目覆盖**：项目规则另有明确规定时从项目规则，其余照本节。

## PLAN → REVIEW → READY

1. 先写 Goal / 边界，再从它拆 task；不能先列实现步骤再反推 Goal。产出给人读或给下游用时，Goal 写明读者，
   「设计」里附一份手写的最终产出样例；输入、schema 与筛选标准从样例倒推。产出供读者在之后的工作里
   反复取用（知识库、工具、数据、服务）时，第一个退出条件写一次可观察的使用：读者在真实工作里用上了产出（例：
   某个真实项目的 plan 引用了它，某次真实运行用了它的输出），不写「机制正确」或「判据能算出数」；使用发生后记进
   当前结论并链接证据。回答一个问题的 Goal（判定、对比、复现、修 bug）退出条件仍是那个结论。human 提出的实现方案默认采用，
   但和 agent 自己的方案一样要对照 Goal；与 Goal 冲突时（包括 Goal 变了之后）先指出冲突，由 human 决定改还是留，
   不自行替换，也不默默照做。
2. 写设计：
   - 先按机制名搜一次 memory 的 `rejected`。
   - 设计节写选定的方案，不用待回答的问题清单或完成检查点代替。最终方法还定不下来时，选定一个能消除这份不确定性的 probe
     写成设计；纯查询、调研整理与写方案直接做，不建交付物是设计本身的 task。
   - 多段管线先让每段的最简版本端到端跑通，再加深其中一段。供读者反复取用的产出，最简版本还要被读者用上一次才加深；
     测量与判据、健壮性、演练、第二层抽象都算加深。还没被用上时，下一个 task 只做让它被用上的事：接进一个真实项目、
     改读法、删掉挡路的步骤。
   - 一个 task 最多跨一个未验证假设；失败后无法定位哪条假设错了，就先拆 probe / inspection。
   - 交给被测方的题目、数据、样本或请求，连同决定它们的 schema / 模板 / 候选定义，在实现前写进设计并附
     渲染样例；改它们等于改设计。
   - 删除或放宽一道门时，写明它防的风险由哪道检查接替。
   - 改代码的 task，设计写明落在哪个现有 owner 及为什么不放别处、按机制名搜到并复用的现有机制、要改的文件，
     以及每条行为由哪个测试钉住；局部可逆的选择留给实现。
   - 模块契约：改动新增跨 run 持久的状态、读写或权限边界、并发写者，或有多个调用方的接口时，实现前展开成约一页：
     唯一 owner 与职责、数据布局与生命周期、谁以什么模式读写、不变量（各配一个测试）、并发与失败行为、
     不做的事。Gate 上 human 只审其中的不变量与取舍，不审代码布局。
   - 类级设计：改代码的工作引入新抽象、给仓库已有的概念（一个检查、一个状态读取、一个 registry）再写一份实现，或改跨模块
     使用的接口时，拆 task 前先写现状与目标类图、关键场景的一张时序图（画法见 `code-to-uml-diagram`）；
     每个概念一个 owner，写明替换或复用哪份现有实现；最小迁移顺序，每步可独立合并。它写进第一个 task 的设计，
     那次 plan review 就是独立架构评审：目标是否每个概念一个 owner、第一版该不做什么，修正记进 plan。
     这个 task 关闭前不拆后续 task。
3. 只把最近 1–2 项写进 `task.md`，状态为 `📝 proposed`，设计节里写 `- rev：rN` 绑定 plan 的 revision。task 行链接它的设计：feature 文档里以
   task id 开头的标题段；CLOSE 删除它，`init` 拒绝别处的设计与 `features/` 外的新 plan（边界见 `design.md` 的 Feature 与 exp 文档）。
4. 配置 reviewer 时，提交后在同一轮运行 `plan-review`，不留到下一轮：task 在它绑定的每个 revision 下审一次，
   同一 revision 内改设计不重审。Harness 启用、未配 pager 时，plan 停在 `proposed` 而审查没做完，stop hook 不放行。
   reviewer 只给准入意见，分 `must`（不改就方向错、结论错或白跑昂贵实验）与 `suggest`（严谨性），各最多 3 条。
5. 逐条回应 `must`：照改后 `plan-review --respond <task> --item N=applied`；只在与事实不符时
   `--item N=reject --reason "<事实>"`，只驳一次。`suggest` 酌情改或跳过，不必回应。不回审。
   reviewer 能定时（判据见 `when-to-stop` 的「问 human 之前先自己判断，再过 reviewer」）不问 human，直接进第 6 步；
   否则用平台的结构化提问能力给 human：`approve / revise / continue automatically`。问题里先给 plan 的「设计」与
   「当前结论」，再附逐 task 意见与回应；task 的执行步骤不进问题。
   带 `human: true` 的 must 由 human 选，用 human 原话 `plan-review --approve <task> --reason` 记下；
   human 要求重审用 `--again`。reviewer 报告缺失或失败、交给 human 的问题未批准时，不实验、不改实现，
   只做 `task-state` 的 proposed 定义允许的准备。
6. human 批准后 `Plan Review: approved`，reviewer 能定时写 `Plan Review: unreviewed`；
   最高优先级行转 doing，其余转 todo。
7. 项目有多个 Goal 时，第一个 Goal 的 Gate 同时对齐 `task.md` 的主线一节（格式见 `task-state`），
   human 批准后写 `Mainline Review: approved`。

远期路线只作为 `task.md` 的候选与触发项（格式见 `task-state`）；plan 只放 Goal、边界、当前结论与证据，
不放执行项。每项拿到 evidence 后再生成下一项，不一次写死整条路线。

## Goal Review

项目显式配置 action count 或 elapsed time attention、并触发 `goal_review_due` 时，先回答并落盘。
失败归 `when-to-stop`，evidence stale 直接重新验证，都不先做 Goal Review：

1. 当前 Goal 是什么；
2. 新 evidence 改变了什么；
3. 下一动作为什么推进 Goal；
4. `continue / replan / stop`。

- `continue`：更新 plan 的当前结论，调用 `goal-review --decision continue`；
- `replan`：调用 `goal-review --decision replan`，`Plan Revision` +1、review 改 proposed、脉络追加一行，
  按 Human correction 第 3 步处理旧 task 与旧设计，再走 Human Review Gate；
- `stop`：记录边界，调用 `goal-review --decision stop`。

## Human correction

只问进展时读 task、journal 与 evidence 回答，不自动改 revision。`Plan Revision` 只在两处递增：这里的 human 纠偏，
与 Goal Review 的 `replan`。往下拆 task、更新当前结论或脉络、按 must 改设计都不升版，新 task 绑当前 `rN`；
Harness 拒绝没有 `pause --require-revision` 或 replan 记录的升版。形成 Goal / scope / 优先级修改后：

1. `pause --require-revision --reason "<纠偏>"`；
2. Goal 本身的修改写进 `task.md`；受影响的每份 feature 更新目标与边界，revision +1、review 改 proposed，脉络追加一行旧 Goal → 新 Goal 及原因；
3. 旧 task 逐项保留、blocked 或 dropped；从旧 Goal 推出的设计与评测数据（筛选标准、prompt、模板、阈值、
   标注集）在 plan 里逐项标 keep / revise / drop，human 提出的按第 1 步处理；旧标注能否作证据见
   `experiment-design` 的验收门。新 task 绑定新 `rN`；保留的 task 核对设计后改绑新 `rN`，因此重审一次，
   暂留旧 `rN` 的 blocked task 不重审；
4. 独立 plan review 后按 Gate 第 5 步恢复唯一 doing，再 `resume`；task reviewer 选了 `ask_human` / `stop`
   而 human 决定开新 task 时，human 把它批为 `🔬 doing` 后直接 `init`，不用 `disable`。

对话里的「明白」不算 RECONCILE；四步落盘后才继续。

## CLOSE

**CLOSE 不只是追加摘要，还要让已闭合记录退出活跃工作集。**

CLOSE 分两段：

1. **locked verifier 前**：worker 按 `experiment-design` 的 CLOSE self-audit 回读本 task 完整 diff，
   精炼文档并处理临时脚本。
2. **verifier 通过后**：收口结论、归档已闭合记录。

verifier 通过后，项目配置了 reviewer 时（谁写脉络行见「脉络」一节）Harness 自动运行 `harness review`，
worker 只做事实核对；prompt 与决策格式见 `harness/prompts/task_review.md`。标 done、删除关闭 task 的标题段、
把指向它们的链接改成纯文字由 Harness 在 reviewer 决定落盘后完成，reviewer 与 worker 都不手工删。此外：

1. 把该 task 的多轮实验合并成一个 task 结论，更新「当前结论」，把它并入脉络的当前阶段行，换方向时开新行；
2. exp 的 Experiment Log 已收口行改为 `promoted / superseded`，留到 Goal 冻结；active Experiment Log 超过 10 行是
   漏执行告警，不是按行截断规则；
3. 通知 `task-state` 归档 closed task（`progress.md` 的旧交接段由 Harness 在 CLOSE 时移进 archive），通知
   `agent-memory` 只保留未来仍会改变选择的结论、`disproved / rejected` 与证据指针；
4. 本 task 的临时文件（kit、workspace、本地 run 目录、job 清单、PR 草稿、task 专用 verifier）都放
   `.harness/tasks/<task_id>/`，要留的在 locked verifier 前移出。配置 reviewer 时 Harness 在决定落盘后删除它，
   未配置时 CLOSE 末尾运行 `clean-task`；`status` 的 `strays` 列出 `.harness/` 里不归 Harness 的条目，逐条移走或删除。
   关闭 task 的 `verify` / `review` / `clean-task` 输出与 `status` 的 `leftovers` 列出 `.agent-loop/` 里名字带已关闭
   task id、或在已关闭 Goal 的旧位置 plan 目录、又没被现行文档提到的文件：项目事实移进项目被跟踪的文档，只证明 task
   通过的验收证据记进 exp 的 Experiment Log，其余删除；被误报的长期工具在 `memory/facts.md` 提一句即不再报。逐 run 表的要求归 `experiment-design`。

### 主线交接

- reviewer 对主线 Goal 选 `stop` 时，把它在主线表的行改 `✅ done`、下一行改 `▶ next`，为 `▶ next` 的 Goal
  写它的 feature 文档、跑独立 plan review 再开工，不停在 DONE；`Mainline Review` 不是 `approved` 时交 human。
- `▶ next` 的主线行超过 7 天没改过时，写 feature 文档前先核对它引用的 issue 仍 open、human 原话仍成立；
  不成立就按 `task-state` 的到期处理把它标 `❌ dropped`，不写 plan。
- 新 Goal 进主线要 human 显式批准：主线行的问题格引用 human 说「做」或「开始」的原话与出处（issue 评论，或调度窗口转述）。
  「不在本轮修」「推迟」「以后再说」不进主线：issue 保持 open、不挂 Goal，或直接关闭。
- 增删 Goal 或改顺序是 `replan`：`Mainline Review` 改 `proposed`，交 human。
- 由故障或基础设施问题引出的 Goal 是支线：不进主线表，plan 头部写 `Side of: <主线 Goal>` 与预算，
  开支线要 human 批准。

feature 完成或 pivot 时冻结它的 feature 文档为 as-built：只留首屏、Goal、设计、当前结论、适用边界与脉络，首屏 `下一步`
写「已冻结」加后继 feature 的链接，没有后继写「无后继」；exp 文档留实验节与 Experiment Log，
两份都不删、不搬。主线行改 `✅ done` 时，否定发现进 memory 的 `rejected`。在途 Goal 用旧位置 plan 时，冻结后它的目录只剩
plan document，其它文件进入 `leftovers`，按 CLOSE 第 4 步处理；暂停中的 Goal 不进。具体格式分别归
`experiment-design`、`task-state`、`agent-memory`，本 skill 只拥有 task / Goal 的退役时机。
