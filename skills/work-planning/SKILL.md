---
name: work-planning
description: >-
  把 Goal 落成一份 feature 文档与同名 exp 文档、最近 1–2 个渐进 task 与 Human Review Gate；
  处理 Plan Revision、Goal Review 和人工纠偏后的 RECONCILE。
  Use for new goals, proposed plans, plan review, goal refresh, or user corrections.
---

# Work Planning

本 skill 是 planning Policy。状态转移归 `harness/protocol.py`，task schema 归 `task-state`，实验假设与判据归 `experiment-design`。

## 文档

各文档写什么、放哪、怎么拆，归 `project-docs`；写设计（第 2 步）、RECONCILE 与 CLOSE 时同读它。

## 讨论

human 说「brainstorm / 讨论 <议题>」时开：局外与局内两个 agent 就一个还没定的问题或实验来回几轮，收敛成双方都同意的实验设计。它不是裁决：agent 自己要定的事照 `when-to-stop` 一轮裁决。

- **各方**：局外是项目的 reviewer 命令（未配置时同 `when-to-stop` 的默认 reviewer），在独立上下文里先起草，只给议题、约束、human 已定的 Goal 与可定位的事实（exp 读数、feature 的当前结论），不给 agent 的路线推荐；局内是项目会话的 agent，带全部上下文回应。
- **讨论稿**：`discussions/<YYYY-MM-DD>-<议题短名>.md`，一个议题一份。头块写议题原话、输入版本、状态（进行中 / 收敛 / 截止）；正文是当前设计，交给局外的完整请求与讨论记录放文末。
- **回应**：每次一节 `### R<n> 局外|局内 <模型>`，由带 ID 的条目组成（D1、D2…，之后只引 ID），每条写立场、主张、依据、处置；反对写出什么结果能定这个分歧。共识不是证据：事实问题写成待核查，进设计作 probe。
- **上限**：局外起草一次，之后双方各至多 3 次回应；讨论不跑实验、不占机时。双方回应过同一版设计、没有未处置的异议即收敛。
- **收尾**：收敛后把设计写进对应 feature 的设计节（新问题按下一节开 feature），脉络链接讨论稿，两者一起提交，照常走 plan review。到上限仍有分歧时记截止，把分歧点与双方的主张、依据写成一道结构化提问交 human，这是讨论里唯一找 human 的情况；human 定后同样落进 feature。
- **项目覆盖**：项目规则另有明确规定时从项目规则，其余照本节。

## PLAN → REVIEW → READY

1. 先写 Goal / 边界，再从它拆 task；不能先列实现步骤再反推 Goal。产出给人读或给下游用时，Goal 写明读者，「设计」里附一份手写的最终产出样例；输入、schema 与筛选标准从样例倒推。产出供读者在之后的工作里反复取用（知识库、工具、数据、服务）时，第一个退出条件写一次可观察的使用：读者在真实工作里用上了产出（例：某个真实项目的 plan 引用了它，某次真实运行用了它的输出），不写「机制正确」或「判据能算出数」；使用发生后记进当前结论并链接证据。回答一个问题的 Goal（判定、对比、复现、修 bug）退出条件仍是那个结论。human 提出的实现方案默认采用，但和 agent 自己的方案一样要对照 Goal；与 Goal 冲突时（包括 Goal 变了之后）先指出冲突，由 human 决定改还是留，不自行替换，也不默默照做。
2. 写设计：
   - 先按机制名搜一次 memory 的 `rejected`。
   - 设计节写选定的方案，不用待回答的问题清单或完成检查点代替。最终方法还定不下来时，选定一个能消除这份不确定性的 probe写成设计；纯查询、调研整理与写方案直接做，不建交付物是设计本身的 task。
   - 多段管线先让每段的最简版本端到端跑通，再加深其中一段。供读者反复取用的产出，最简版本还要被读者用上一次才加深；测量与判据、健壮性、演练、第二层抽象都算加深。还没被用上时，下一个 task 只做让它被用上的事：接进一个真实项目、改读法、删掉挡路的步骤。
   - 一个 task 最多跨一个未验证假设；失败后无法定位哪条假设错了，就先拆 probe / inspection。
   - 交给被测方的题目、数据、样本或请求，连同决定它们的 schema / 模板 / 候选定义，在实现前写进设计并附渲染样例；改它们等于改设计。
   - 删除或放宽一道门时，写明它防的风险由哪道检查接替。
   - 改代码的 task，设计写明落在哪个现有 owner 及为什么不放别处、按机制名搜到并复用的现有机制、要改的文件，以及每条行为由哪个测试钉住；局部可逆的选择留给实现。
   - 模块契约：改动新增跨 run 持久的状态、读写或权限边界、并发写者，或有多个调用方的接口时，实现前展开成约一页：唯一 owner 与职责、数据布局与生命周期、谁以什么模式读写、不变量（各配一个测试）、并发与失败行为、不做的事。Gate 上 human 只审其中的不变量与取舍，不审代码布局。
   - 类级设计：改代码的工作引入新抽象、给仓库已有的概念（一个检查、一个状态读取、一个 registry）再写一份实现，或改跨模块使用的接口时，拆 task 前先写现状与目标类图、关键场景的一张时序图（画法见 `code-to-uml-diagram`）；每个概念一个 owner，写明替换或复用哪份现有实现；最小迁移顺序，每步可独立合并。它写进第一个 task 的设计，那次 plan review 就是独立架构评审：目标是否每个概念一个 owner、第一版该不做什么，修正记进 plan。这个 task 关闭前不拆后续 task。
3. 只把最近 1–2 项写进 `task.md`，状态为 `📝 proposed`，设计节里写 `- rev：rN` 绑定 plan 的 revision。task 行链接它的设计：feature 文档里以task id 开头的标题段；CLOSE 删除它，`init` 拒绝别处的设计与 `features/` 外的新 plan（边界见 `design.md` 的 Feature 与 exp 文档）。
4. 配置 reviewer 时，提交后在同一轮运行 `plan-review`，不留到下一轮：task 在它绑定的每个 revision 下审一次，同一 revision 内改设计不重审。Harness 启用、未配 pager 时，plan 停在 `proposed` 而审查没做完，stop hook 不放行。reviewer 只给准入意见，分 `must`（不改就方向错、结论错或白跑昂贵实验）与 `suggest`（严谨性），各最多 3 条。
5. 逐条回应 `must`：照改后 `plan-review --respond <task> --item N=applied`；只在与事实不符时`--item N=reject --reason "<事实>"`，只驳一次。`suggest` 酌情改或跳过，不必回应。不回审。reviewer 能定时（判据见 `when-to-stop` 的「问 human 之前先自己判断，再过 reviewer」）不问 human，直接进第 6 步；否则用平台的结构化提问能力给 human：`approve / revise / continue automatically`。问题里先给 plan 的「设计」与「当前结论」，再附逐 task 意见与回应；task 的执行步骤不进问题。带 `human: true` 的 must 由 human 选，用 human 原话 `plan-review --approve <task> --reason` 记下；human 要求重审用 `--again`。reviewer 报告缺失或失败、交给 human 的问题未批准时，不实验、不改实现，只做 `task-state` 的 proposed 定义允许的准备。
6. human 批准后 `Plan Review: approved`，reviewer 能定时写 `Plan Review: unreviewed`；最高优先级行转 doing，其余转 todo。
7. 项目有多个 Goal 时，第一个 Goal 的 Gate 同时对齐 `task.md` 的主线一节（格式见 `task-state`），human 批准后写 `Mainline Review: approved`。

远期路线只作为 `task.md` 的候选与触发项（格式见 `task-state`）；plan 只放 Goal、边界、当前结论与证据，不放执行项。每项拿到 evidence 后再生成下一项，不一次写死整条路线。

## Goal Review

项目显式配置 action count 或 elapsed time attention、并触发 `goal_review_due` 时，先回答并落盘。失败归 `when-to-stop`，evidence stale 直接重新验证，都不先做 Goal Review：

1. 当前 Goal 是什么；
2. 新 evidence 改变了什么；
3. 下一动作为什么推进 Goal；
4. `continue / replan / stop`。

- `continue`：更新 plan 的当前结论，调用 `goal-review --decision continue`；
- `replan`：调用 `goal-review --decision replan`，`Plan Revision` +1、review 改 proposed、脉络追加一行，按 Human correction 第 3 步处理旧 task 与旧设计，再走 Human Review Gate；
- `stop`：记录边界，调用 `goal-review --decision stop`。

## Human correction

只问进展时读 task、journal 与 evidence 回答，不自动改 revision。`Plan Revision` 只在两处递增：这里的 human 纠偏，与 Goal Review 的 `replan`。往下拆 task、更新当前结论或脉络、按 must 改设计都不升版，新 task 绑当前 `rN`；Harness 拒绝没有 `pause --require-revision` 或 replan 记录的升版。形成 Goal / scope / 优先级修改后：

1. `pause --require-revision --reason "<纠偏>"`；
2. Goal 本身的修改写进 `task.md`；受影响的每份 feature 更新目标与边界，revision +1、review 改 proposed，脉络追加一行旧 Goal → 新 Goal 及原因；
3. 旧 task 逐项保留、blocked 或 dropped；从旧 Goal 推出的设计与评测数据（筛选标准、prompt、模板、阈值、标注集）在 plan 里逐项标 keep / revise / drop，human 提出的按第 1 步处理；旧标注能否作证据见`experiment-design` 的验收门。新 task 绑定新 `rN`；保留的 task 核对设计后改绑新 `rN`，因此重审一次，暂留旧 `rN` 的 blocked task 不重审；
4. 独立 plan review 后按 Gate 第 5 步恢复唯一 doing，再 `resume`；task reviewer 选了 `ask_human` / `stop`而 human 决定开新 task 时，human 把它批为 `🔬 doing` 后直接 `init`，不用 `disable`。

对话里的「明白」不算 RECONCILE；四步落盘后才继续。

## CLOSE

**CLOSE 不只是追加摘要，还要让已闭合记录退出活跃工作集。**

CLOSE 分两段：

1. **locked verifier 前**：worker 按 `experiment-design` 的 CLOSE self-audit 回读本 task 完整 diff，精炼文档并处理临时脚本。
2. **verifier 通过后**：收口结论、归档已闭合记录。

verifier 通过后，项目配置了 reviewer 时（谁写脉络行见 `project-docs` 的「脉络」）Harness 自动运行 `harness review`，worker 只做事实核对；prompt 与决策格式见 `harness/prompts/task_review.md`。标 done、删除关闭 task 的标题段、把指向它们的链接改成纯文字由 Harness 在 reviewer 决定落盘后完成，reviewer 与 worker 都不手工删。此外：

1. 把该 task 的多轮实验合并成一个 task 结论，更新「当前结论」，把它并入脉络的当前阶段行，换方向时开新行；
2. exp 的 Experiment Log 已收口行改为 `promoted / superseded`，留到 Goal 冻结；active Experiment Log 超过 10 行是漏执行告警，不是按行截断规则；
3. 通知 `task-state` 归档 closed task（`progress.md` 的旧交接段由 Harness 在 CLOSE 时移进 archive），通知`agent-memory` 只保留未来仍会改变选择的结论、`disproved / rejected` 与证据指针；
4. 本 task 的临时文件（kit、workspace、本地 run 目录、job 清单、PR 草稿、task 专用 verifier）都放`.harness/tasks/<task_id>/`，要留的在 locked verifier 前移出；配置 reviewer 时 Harness 在决定落盘后删除它，未配置时 CLOSE 末尾运行 `clean-task`。输出与 `status` 报的 `strays`、`leftovers`（定义见 `design.md`）逐条处理：项目事实移进项目被跟踪的文档，只证明 task 通过的验收证据记进 exp 的 Experiment Log，其余删除；被误报的长期工具在`memory/facts.md` 提一句即不再报。逐 run 表的要求归 `experiment-design`。

### 主线交接

- reviewer 对主线 Goal 选 `stop` 时，把它在主线表的行改 `✅ done`、下一行改 `▶ next`，为 `▶ next` 的 Goal写它的 feature 文档、跑独立 plan review 再开工，不停在 DONE；`Mainline Review` 不是 `approved` 时交 human。
- `▶ next` 的主线行超过 7 天没改过时，写 feature 文档前先核对它引用的 issue 仍 open、human 原话仍成立；不成立就按 `task-state` 的到期处理把它标 `❌ dropped`，不写 plan。
- 新 Goal 进主线要 human 显式批准：主线行的问题格引用 human 说「做」或「开始」的原话与出处（issue 评论，或调度窗口转述）。「不在本轮修」「推迟」「以后再说」不进主线：issue 保持 open、不挂 Goal，或直接关闭。
- 增删 Goal 或改顺序是 `replan`：`Mainline Review` 改 `proposed`，交 human。
- 由故障或基础设施问题引出的 Goal 是支线：不进主线表，plan 头部写 `Side of: <主线 Goal>` 与预算，开支线要 human 批准。

feature 完成或 pivot 时按 `project-docs`「冻结」把它的文档冻结为 as-built。主线行改 `✅ done` 时，否定发现进 memory 的 `rejected`。在途 Goal 用旧位置 plan 时，冻结后它的目录只剩plan document，其它文件进入 `leftovers`，按 CLOSE 第 4 步处理；暂停中的 Goal 不进。具体格式分别归`experiment-design`、`task-state`、`agent-memory`，本 skill 只拥有 task / Goal 的退役时机。
