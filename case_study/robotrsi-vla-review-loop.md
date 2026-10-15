# Case：robotRSI VLA 执行层，plan review 在廉价 CPU 探针上反复 revise，收益低于成本

> 时间：2026-10-14。执行：Cursor 里的 Claude（agent-loop rules + skills + Harness）；reviewer：WSL Codex
> `gpt-6-astra`，经 Harness 的 plan review 与 task boundary review 调用；human 在 Human Review Gate 批准。
> 远端一个 8 卡节点，全程只用 CPU。本文记录问题，部分已修。

## 结论

**评审意见大多成立，前几轮还挖出了真问题；但同一道 plan review 门被用在 ≤ 20 分钟的 CPU 探针上，每轮 revise
都逼出一个新 revision 与一次全量重审，后几轮的意见只是在给探针补边界条件。** 一天里 plan 从 r1 改到 r8，
跑了 9 次 plan review、3 次 task review；真正产出实验证据的只有 3 次采样运行，合计不到 10 分钟 CPU。
human 问"是不是陷在 review–revise 里打转"之后，才手动叫停。

机制上缺五样东西：

1. **门槛不分成本**：20 分钟的 CPU 探针和 80 小时的 GPU 实验，走同一道 plan review；
2. **刹车只是告警**：`BRAKE_THRESHOLD = 3` 只在 JSON 里加一行 warning，不强制停，计数还会被中间的一次 accept 或一次 exec 清零；
3. **一行修改也要整轮重审**：verdict 只有 accept / revise，改一句话就要 revision +1、全量重审，重审还会把已批准、未改动的 task 一起再审一遍；
4. **human 不能免审**：配置了 reviewer 时，没有 review 记录就拒绝 `init`，human 已经拍板也只能空跑一次 review；
5. **reviewer 读不到项目外的证据**：被测代码在兄弟仓库或远端节点上，reviewer 就报"证据缺失"。同一原因卡了 3 次。

## 背景

robotRSI 想给 RoboRSI 加一个 VLA 接触执行层：π0.5 作为 `vla_pick` 工具。MVP 前有四个 CPU 前置探针：
- v0：请求样例；
- v0b：独立参考臂对比；
- v0e：指令来源复核；
- v1：控制器中途切换。

每个预算 ≤ 1 小时，多数 20 分钟以内。项目配置了 reviewer，所以每个 Plan Revision 都要独立 plan review。

## 时间线（UTC+8）

| 时间 | 事件 | 结果 |
|---|---|---|
| 14:08 | r1 plan review | revise，4 条：v2 两臂终点不一致、缺渲染样例、成功数推不出契约、v1 缺原生基线。**都成立** |
| 14:13 | r2 | revise，2 条：样例要在批准前给出、动作只覆盖 z 轴。**成立** |
| 14:16 | r3 | 无效：worker 在 review 期间改了 `task.md`，指纹变化，error 记录被缓存，CLI 无法重试，只能手删记录 |
| 14:19 | r3 重跑 | revise，1 条：reviewer 读不到 RoboRSI 源码（在兄弟仓库）。告警：连续 3 次 revise。human 直接批准 |
| 14:53 | v0 采样 → task review | ask_human：参考臂复用了被测的组装函数，不独立。**高价值** |
| 17:29 | r4（v0b） | revise，1 条：v0b 结论外推过头。**成立** |
| 17:31 | r5 | accept |
| 17:45 | v0b 采样 | 真发现：两种指令写法；姿态漂移归因到 settle 协议 |
| ~19:30 | v0c 调研 → task review | ask_human：上游原件在项目外，reviewer 读不到。human 直接采用结论 |
| 19:37 | r6（v0e） | revise，1 条：`select_prompt` 的范围和工具接口冲突。成立 |
| 19:39 | r7 | revise，2 条：扰动样本可能不可区分、v1 配对复测。都是边界条件 |
| 19:42 | human 叫停 | 要求 r8 直接批准 |
| 19:46 | r8 | Harness 拒绝 `init`（没有 review 记录），只能空跑一次：accept，附告警"3 revisions since last exec" |
| 19:51 | v0e 采样 | 一次通过 |

## 哪几轮值，哪几轮不值

| 类别 | 轮次 | 判断 |
|---|---|---|
| 改了设计，防住了真错误 | r1、r2、v0 task review、r4 | 值。参考臂不独立这一条，直接导致了 v0b 的真发现 |
| 证据放在项目外 | r3、v0c task review | 不值。结论不变，只是 reviewer 读不到；human 看一眼就能判断 |
| 给廉价探针补边界条件 | r6（部分）、r7 | 不值。探针本身 20 分钟，边界情况跑一次就会暴露 |
| 纯流程 | r3 无效那次、r8 | 不值。前者是 worker 并发编辑，后者是没有免审入口 |

plan review 本身耗时不长，每次 1.5–2 分钟。代价在别处：human 被叫去做了 5 次批准或决策，worker 每轮都要改文档、改 `task.md`、对齐 revision 号。r6–r8 这三轮在 10 分钟内连续发生，追的都是一个 20 分钟探针的边界。

## 机制漏洞

### 1. 门槛不分成本

- `harness/core.py:170–181`：只要配置了 reviewer，`init` 前每个 Plan Revision 都要有 review 记录，不看 task 的预算或类型。
- `harness/prompts/plan_review.md` 第 3 条"昂贵动作前是否缺廉价前置"，只单向鼓励多加前置；没有反方向的一条："前置本身已经足够廉价，直接跑比审更省"。

### 2. 刹车只是告警

- `harness/plan_review.py:26`：`BRAKE_THRESHOLD = 3`。
- `plan_review.py:111–145`：`_brake_warnings` 只返回字符串列表。连续 revise 计数遇到一次 accept 就断；"自上次 exec 以来的 revision 数"遇到一次 exec 就清零。本例 r4–r5 夹了一次 accept，v0b 又有一次 exec，所以 r6、r7 两次 revise 都没触发告警。
- `skills/work-planning/SKILL.md` 第 5 步只要求把 warnings"原样附上，并问门槛与实验成本是否相称"。worker 在 r3 问过一次；之后告警被清零，就没再问。

### 3. 一行修改也要整轮重审

- 报告按 `(plan_doc, revision)` 去重（`plan_review.py:178–184`）。同一 revision 改了文字也不会重审，所以任何修改都必须 revision +1。
- 每次重审覆盖"最近 1–2 个 proposed task"。v1 在 r3 已被 human 批准；v0 关闭时 task reviewer 把它改回 proposed，于是 r7 又对 v1 提了一条新意见。v1 的设计其实没变。
- verdict 只有 accept / revise，没有"accept，附非阻塞意见"。

### 4. human 不能免审

`core.py:173–176`：Plan Review 为 approved 而没有 review 记录时，抛出"set Plan Review to proposed before approval"。human 明确要求跳过 review，worker 也只能把状态改回 proposed、空跑一次 review、再改回 approved。

### 5. reviewer 读不到项目外的证据

- `plan_review.md` 规定 reviewer 只读 plan 直接链接的文件，缺了就报证据缺失。被测代码在兄弟仓库（RoboRSI fork）、上游原件在 LIBERO / openpi / RLinf / RPent 仓库或远端节点上，链接到不了。
- 3 次被卡：r3、v0 task review、v0c task review。worker 的绕法是把文件快照拷进项目目录（`roborsi/upstream/snapshot-*`）。task reviewer 遇到这种情况还会提一个"补证" successor（v0d），这本身又是一轮新的 plan review。

### 6. review 失败不能重试

`plan_review.py:224–226`：review 期间工作区指纹变了，就记 error。之后同一 revision 直接抛"is incomplete"（`plan_review.py:180–183`），CLI 没有 retry。本例的指纹变化是 worker 并发编辑造成的，worker 只能手删 `.harness/plan-review/<key>-r3.json` 才能重跑。

### 7. ask_human 之后，human 批准也要再升一个 revision

task review 返回 `ask_human` 后，`init` 要求一个比它更新、且 human 已批准的 revision。human 批准的往往就是 reviewer 自己写的 successor，设计一字未改，worker 也只能把 revision +1，于是又触发一次 plan review。

### 8. 复发：通过的廉价探针因证据格式被 ask_human

r8 之后 CPU 探针已不跑 plan review，task review 仍是唯一门槛。c2（18 分钟 CPU）的探针判定 `fix_supports_A`，reviewer 自己从 117 段原始轨迹复算全部门槛也通过，仍判 `ask_human` 并提出补证任务 c3：完整物理状态没有落盘、配对前没有比较完整状态、版本与坐标系没有记录。这三条确实是设计写了而产物没做到的。但补齐之后，不论结果如何，下一条命令都是 v2，因为被测臂和基线的运动不依赖配对，配对只在失败时用来分流。task review 没有"证据有缺口但不影响下一步"这一档，只能把每个缺口升级成一个新 task。

reviewer 还撤回了"两次运行逐值一致"这一条：另一次运行是 runner 被中止后的孤儿结果（见 [stale runner lock](robotrsi-stale-runner-lock.md)），不在 reviewer 的允许输入里。

## 修复

| 漏洞 | 建议 | 状态 |
|---|---|---|
| 门槛不分成本 | task 行声明成本档（如 `cpu-probe ≤ 1h` / `gpu`），低档 task 默认免 plan review、只做执行后的 task review；或由 human 在 Goal 层设定门槛 | 部分实施（[#31](https://github.com/ZJLi2013/agent-loop/pull/31)）：首轮之后任何 task 都可由 human 带意见批准，审查只在设计变化时重跑；首轮审查保留 |
| 刹车只是告警 | 达到阈值后 `plan-review` 返回 `brake`，要求 human 在继续 revise、直接批准、停止三者中选一；计数按"自上次产出新证据的 exec"累计，不被中间的 accept 清零 | 已替换（[#33](https://github.com/ZJLi2013/agent-loop/pull/33)）：每个 task 只审一次，意见分 must / suggest 各最多 3 条，executor 回应 must 后开工，不再回审 |
| 一行修改也要整轮重审 | 增加 `accept_with_notes`，非阻塞意见写进 task 设计、不升 revision；重审只覆盖本 revision 改动过的 task，已批准且设计未变的不重开 | 已实施（[#31](https://github.com/ZJLi2013/agent-loop/pull/31)）：结论按 task 设计摘要存，只改元数据不重审，只审新增或改过的 task；accept 可附意见 |
| human 不能免审 | `plan-review --waive --reason "<human 原话>"` 写一条 `verdict: waived` 的记录，`init` 认可 | 已替换（[#31](https://github.com/ZJLi2013/agent-loop/pull/31)）：`plan-review --approve <task> --reason` 把 human 批准记在 task 当前摘要上 |
| reviewer 读不到项目外证据 | plan 可以声明外部证据路径，Harness 在 review 前把它们按固定版本拷进 `.harness/evidence/`，供 reviewer 读取 | 未实施（t56） |
| task review 不分缺口轻重 | 增加 `accept_with_gaps`：缺口写进下一个 task 的设计（例如 v2 探针顺带落盘状态与版本），不单开补证 task；reviewer 判 ask_human 前先回答"补齐后下一条命令会不会变" | 已实施（[#32](https://github.com/ZJLi2013/agent-loop/pull/32)）：`findings` 记不阻塞的缺口并转给 worker，不升级成补证 task |
| ask_human 后强制升 revision | human 批准 reviewer 写的 successor 时，记录 `approved_by: human` 即可 `init`，不要求新 revision | 已实施（[#32](https://github.com/ZJLi2013/agent-loop/pull/32)）：`init` 只要求 human 批准的 doing task 与 `Plan Review: approved`，不再升 revision |
| review 失败不能重试 | `plan-review --retry` 清除 error 记录后重跑；error 信息里点明是哪些文件改动了 | 未实施（t55） |

## worker 侧的教训

- review 运行期间不要改工作区。本例有两次并发编辑：一次让 r3 作废，一次差点影响 verify。
- 设计里的结论不要写过头。r4、r6 两条意见都是因为"结果为真"那一栏外推得太远。
- 告警出现一次就该停下来，问 human 门槛和成本是否相称，而不是等告警被清零后继续改。

## 证据

均在 `robot_rl_from_zero_to_expert/robotRSI`：

- plan document 与 Plan 记录：`doc/vla-executor.md`（r1–r8 修订说明、「批准 r8，调整 review 门槛」）
- 已关闭 task 的样例与 review 依据：`doc/vla-executor-archive.md`
- plan review 报告：`.harness/plan-review/4c4edec1c14c-r1.json` … `-r8.json`
- task review 决定：`.harness/review/decision.json`（历次）；`.harness/runs.jsonl`
- 绕过读取范围的快照：`roborsi/upstream/snapshot-e4e9024/`、`roborsi/upstream/vla-mvp/`
