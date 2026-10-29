# agent-loop Design


## Goal

让 agent-loop 可以持续演进而不靠向常驻 rule、skill 和单体 Harness 追加分支：新能力有稳定的归属，
已有行为有一个可执行的状态机定义，Cursor、Codex CLI 或自定义 driver 都只承担边界接线。

## 结论

架构收敛为三层：**Stable Kernel / Policies / Adapters**。平台事件先归一为内部 hook protocol，
平台 codec 只翻译输入与输出，不拥有控制逻辑。工作文档默认只有一份 plan document，
需要拆分时只增加 linked sub-exp，不另造 feature / exp 两套生命周期。Kernel 只拥有状态、事件、转移与 guard；
skills 只解释某个状态下怎么做；platform adapters 只接原生事件。新增需求先归类，再决定是配置、policy、
adapter 还是确实需要扩展 kernel。

独立 reviewer 在两个确定性边界运行：Plan Revision 提交后、human 批准前审 task 准入；task
`VERIFIED` 后审证据解释与下一步。plan reviewer 只向 human 提供风险意见，不能批准 plan、关闭 task
或授权执行；human 保留 `approve / revise / stop` 权限。plan review 按 task 审，每个 task 只审一次；
同一 revision 下新增的 task（含 task reviewer 写的 successor）另审。初始化、resume、pager 与无人值守批准都不能绕过有效记录。task reviewer 继续由 Harness 在 verify
后调用，并只报告会改变 `continue / ask_human / stop` 或下一条命令的问题。
固定时间与文件修改 review 不采用——它们没有稳定的决策边界。
Codex、Cursor 等宿主的会话与缓存目录不属于项目状态，也不进入 agent-loop 的生命周期。
上下文与 token 按决策需要花，不按完整性花：常驻面只放路由与当前状态，已关闭记录退出活跃面，
reviewer 只读列出的判据与直接链接的证据，够下结论即停。

## 范围

agent-loop 只维护三类公开保证：

1. 已声明的 task 生命周期：准入、执行、验证、review、暂停、停止、交接、记录退役；
2. 让这些保证在支持的宿主上成立的安装、接线与兼容；
3. 本仓库自身的发行、贡献、安全与缺陷反馈。

| 输入 | 处置 |
|---|---|
| 已有保证被违反，有一次可复现证据 | 收为 defect，不要求第二个项目佐证 |
| 现有状态下的通用决策方法 | 交现有 Policy owner，写出可观察的决策与误触发代价 |
| 理由只是「放得进某个 skill」或「没有 owner」 | 转外部 skill pack，agent-loop 不承担维护 |
| 依赖个人节点池、个人风格或个人调度 | 转用户私有 pack 或执行工具仓库 |
| 新的受控对象、持久身份、权限，或与现有不变量相反 | 先 RFC 或原型 |
| 只有预防性设想，没有公开保证或实际使用方 | 以范围外关闭，写明重新提出的条件 |

外部 pack 经 `~/.agent-loop/packs.txt` 安装；agent-loop 不点名任何包内 skill。本节对新 issue / PR 立即生效；
已发行而落在范围外的 skill 与 rule 迁出到外部 pack，迁出前照常维护，迁移步骤记在 CHANGELOG。

| 需求 | 处置 | 依据 |
|---|---|---|
| [#98](https://github.com/ZJLi2013/agent-loop/issues/98) 新 Goal 的同名 task 继承旧 plan review | 收，defect | 违反保证 1 的准入 |
| [#108](https://github.com/ZJLi2013/agent-loop/issues/108) Windows 上有读者打开 `state.json` 时写入失败 | 收，defect | 违反保证 2 |
| [#46](https://github.com/ZJLi2013/agent-loop/issues/46) 新增画 UML 类图的 skill | 转外部 pack | 理由只是「没有 owner」 |
| [#93](https://github.com/ZJLi2013/agent-loop/issues/93) 自动挑远端 GPU 节点 | 转用户私有 pack | 依赖个人节点池 |
| [#16](https://github.com/ZJLi2013/agent-loop/issues/16) 与确认模式不变量相反的 exploration mode | 先 RFC / 原型 | 与现有不变量相反 |

## 状态模型

决定 agent-loop 允许、拒绝或结束一个动作的持久状态只有下表六个维度。**改变表中任一项的语义就是 Kernel 变更**，
先走 Issue / RFC。参与判定的时序比较写在各维度的「取值」里；只写不读的记录时间、日志、消息文本与 hook payload
不参与判定。

| 维度 | 身份 | 取值 | 谁能改 | 存在哪 | 契约测试 |
|---|---|---|---|---|---|
| task 实例 | task id 按原字符串匹配，大小写不同却共享同一记录文件时拒绝；review 只对它审过的 `plan_doc`（规范化的项目相对路径）有效 | 未审 / 已审 / 需重审（任一 `again[].at` 不早于最后一次 review 的 `at`）/ must 未回应 / 待 human 批准（没有不早于该 review 的 `approvals[].at`）；`Plan Revision`、task `rN` 与锁定的 `plan_revision` | plan reviewer 写 findings；executor `--respond`；human `--approve` / `--again`；worker 或 human 改 revision | `.harness/plan-review/tasks/<id>.json`；plan document 头部；`task.md` 的 task 行（已归档时读 `archive/tasks.md`）；`state.json` | `tests/test_plan_review.py` |
| 执行尝试 | 一个 `.harness/` 一次一个 active task；每次运行一个 `run_id` | phase（下表）；`current_run_id` 与 `runner_pid` 表示占用；`verify_attempts` / `wall_seconds_used` 对预算；`verified_fingerprint`；`stop_report_requested` | runner 与 verifier 经 Harness 转移；`disable` | `state.json`；`config.json`（verifier `argv` / `timeout_seconds` / `expect_regex` / `forbid_regex`、budget、limits，摘要锁在 `config_sha256`）；`artifacts/<run_id>/start.json`；`.harness/lock` | `tests/test_protocol.py`、`tests/test_harness.py` |
| 决策权限 | 每个 human 检查点一个 `page.key`；`review_failed` 的 key 含 `review.run_id` | `Plan Review`: `approved` / `unreviewed` / `proposed`；pause（`human` / `goal_review`，`require_revision`）；`review.attempts`（异议一次）；`review.report_requested`（reviewer 失败只报一次） | human 经 Gate、`pause`、pager 回复；无人值守自批只能写 `unreviewed`；init 锁定 reviewer 与 pager 命令 | plan document 头部；`.harness/pause.json`；`state.json` 的 `review` / `page`；`.harness/pager-state.json`；`config.json` 的 `reviewer` / `pager` | `tests/test_harness_pause.py`、`tests/test_page.py` |
| 调度 | 决策的 `verify_run_id` 等于 `last_run_id` 才算本次已审 | `continue` / `ask_human` / `stop` 与 `next_task`；task 行 `🔬 doing`；主线 `▶ next` / `✅ done` 与 `Mainline Review`；Goal attention 到期（`actions_since_goal_review` 达到 `after_actions`，或距 `last_goal_review_at`、没有时距 `created_at` 的秒数达到 `after_seconds`） | task reviewer 写决策，Harness 校验后落盘；human 与 worker 改 `task.md`；runner 累加计数 | `state.json` 的 `review`；`.harness/review/decision.json`；`task.md` 的 task 表与 `## 主线`；`config.json` 的 `goal_review` | `tests/test_review.py`、`tests/test_attention.py` |
| 会话归属 | 会话 id，依次取 `AGENT_LOOP_SESSION_ID`、`CURSOR_CONVERSATION_ID`、`DSH_SESSION_ID` | `owner` 等于请求的会话、属于别的会话或为空；Cursor 会话绑定的项目；followup 已发 | init 写 `owner`；Cursor hook 读 `task.md` 时绑定；completion gate 写 followup 标记 | `state.json` 的 `owner`；系统 temp 的 `agent-loop-cursor-sessions/<sha256>`、`agent-loop-followups/<sha256>` | `tests/test_harness_stop.py`、`tests/test_cursor_session_scope.py` |
| 记录寿命 | closed task 按 task id 归档 | active / `✅ done` / `❌ dropped`；task 设计段在 plan 中或在 `<plan>-archive.md`；scratch 存在或已删；journal 与 artifacts 条数 | Harness CLOSE（reviewer 决策落盘后，或 `clean-task`）；runner 按 `limits` 裁剪 | `task.md` → `archive/tasks.md`；plan → `<plan>-archive.md`；`.harness/tasks/<id>/`；`runs.jsonl`、`artifacts/` | `tests/test_records.py`、`tests/test_scratch.py` |

已知与实现不符：task 设计段只在标题首词是 task id 时退役，写在主题标题下的设计不退役（[#123](https://github.com/ZJLi2013/agent-loop/issues/123)）。

执行尝试的 phase 与转移：

| State | 含义 |
|---|---|
| `PROPOSED` | plan / task 等待 review |
| `READY` | plan 已批准，可选择下一动作 |
| `RUNNING` | runner 正在执行命令 |
| `PAUSED` | 等待 human review，拒绝新命令 |
| `VERIFYING` | 独立 verifier 正在运行 |
| `VERIFIED` | evidence 通过且 fingerprint 未变化 |
| `FAILED` | 当前动作失败，可 diagnose / repair |
| `STOPPED` | budget 用尽、禁用或 Auto-Stop |

| Event | 典型转移 |
|---|---|
| `PLAN_APPROVED` | `PROPOSED → READY` |
| `RUN_STARTED / RUN_FINISHED` | `READY|FAILED → RUNNING → READY` |
| `VERIFY_STARTED / VERIFY_PASSED` | `READY|FAILED → VERIFYING → VERIFIED` |
| `VERIFY_FAILED` | `VERIFYING → FAILED` |
| `USER_CORRECTION / PAUSE_REQUESTED` | active state → `PAUSED` |
| `PLAN_RESUMED` | `PAUSED → READY` |
| `EVIDENCE_STALE` | `VERIFIED → FAILED` |
| `BUDGET_EXHAUSTED / DISABLED` | active state → `STOPPED` |

跨维度的 guard 是可执行条件，不写成 agent 自觉：

- plan document `Plan Revision` = task `rN` = runtime revision；
- `Plan Review` 是 `approved` 或 `unreviewed`；有待 human 决定的 review 项时不认 `unreviewed`；
- task 有有效的 plan review：最后一条记录由 plan reviewer 写、对应当前 `plan_doc`、之后没有 `--again`，
  `must` 全部回应，human 项有不早于 review 的 `--approve`；
- pause request 不存在；
- `config.json` 的摘要等于 init 时记下的 `config_sha256`；
- attempt / wall budget 尚有余额，用尽后只要求一次 Auto-Stop Report；
- task reviewer 的决策落盘前，runner 与下一 task 的 init 都被拒绝；
- verifier 通过且 workspace fingerprint 未变化；
- 请求的会话不是 `owner` 时，gate 不写状态、不发 followup。

## Architecture

```text
                         design.md
              states / events / transitions / guards
                              │
                    ┌─────────┴─────────┐
                    │   Stable Kernel   │
                    │ protocol + state  │
                    └─────────┬─────────┘
                              │ current state
              ┌───────────────┴────────────────┐
              │            Policies            │
              │ planning / experiment / stop   │
              │ memory / unattended / writing  │
              └───────────────┬────────────────┘
                              │ actions
              ┌───────────────┴────────────────┐
              │            Adapters             │
              │ platform codecs / runner / git  │
              │ verifier / stdout journal       │
              └─────────────────────────────────┘
```

### Stable Kernel

Kernel 不知道 plan 文档怎么写、实验用什么指标，也不知道任何平台的 hook JSON。它只拥有[状态模型](#状态模型)
里的状态、转移与 guard。

### Policies

Policy 回答「这个状态下怎么做」，不重新定义转移：

| Policy | Owner |
|---|---|
| Goal → plan document → proposed task → review | `work-planning` |
| 新增持久状态或读写边界前的模块契约 | `work-planning` |
| SELECT / task 状态与检查点 | `task-state` |
| 实验假设、判据、记录 | `experiment-design` |
| 失败分类与 Auto-Stop | `when-to-stop` |
| 事实、结论与经验检索 | `agent-memory` |
| 无人值守的 review / blocked 处理 | `agent-loop` 的最小常驻 policy |

`work-planning` 拥有 plan document 的稳定头部；`experiment-design` 只拥有 Experiment Log /
sub-exp 的假设、判据与证据。一个知识点只能有一个 owner；其它位置只留路由或链接。

### One plan document

默认一份文档同时承担 plan 与 evidence index：

```text
Plan Revision / Plan Review
Goal
当前结论
脉络（每个关闭的 task、每次 Plan Revision 一行，只追加）
系统 / Pipeline（确实存在才写）
Experiment Log
```

单个实验直接追加到 `Experiment Log`。只有同一 Goal 下出现多个独立实验、详细日志开始遮蔽稳定头部、
或需要并行维护时，才拆 linked `sub-exp/<id>.md`；plan document 始终保留结论与链接。
Harness 参数叫 `plan_doc`，不关心文件名是 feature、exp 还是其它名字。

task CLOSE 时，Experiment Log 的多轮记录合并为脉络里的一行；已收口内容进入 linked archive，
不继续占用活跃表。脉络由做决定的一方当场写，CLOSE、replan 与冻结都保留。Goal CLOSE / pivot 时冻结 plan 为 as-built。sub-exp 不删，但只按 evidence 指针读取；
run 输出的位置与删除时机见 `experiment-design` 的 CLOSE self-audit。closed task 与旧交接快照同样移出活跃
`.agent-loop/task.md` / `progress.md`；`disproved / rejected` 因仍会阻止重复试错而保留在 memory。

CLOSE self-audit 是 `experiment-design` 的 Policy 步骤，不增加状态：worker 在 locked verifier 前回读
本 task 的完整 diff，删除过程性文案和一次性脚本，保留事实、决策分析、结论与 evidence。verifier
因此只验证最终 workspace；验证后再由 `work-planning` / reviewer 收口结论与下一步。

### Goal attention refresh

Goal Review 是 PAUSED 的一种 reason，不新增 Kernel state。默认 profile 不按时间、动作数或失败暂停；
项目确实需要固定 attention refresh 时，可显式配置：

- 距上次 review 已完成 N 次 runner action；
- 距上次 review 超过 N 分钟。

失败归 `when-to-stop` 的诊断、自修与停机分流；evidence stale 保持 `FAILED` 并直接要求重新运行 locked verifier。

下一动作开始前，Policy 必须落盘四项：当前 Goal、新 evidence、下一动作为何推进 Goal、
`continue / replan / stop`。`continue` 更新 review 计数并 resume；`replan` 进入现有 revision /
review / RECONCILE；`stop` 进入 Auto-Stop。单条命令执行期间没有模型 turn，timer 只写 pause request，
反思发生在安全轮询点或命令结束后。命令与 reviewer 运行期间不持状态锁：`running` / `verifying` 加 run id 与 runner pid、
`review_running`、`plan-review/running.json` 表示占用，status、pause 与 gate 照常可用，第二次运行被拒；锁只包住状态的读写。抢锁失败时等几秒，再报出持有者的 pid、命令与启动时间；持有者已不在时给出删锁命令，
Harness 不自动回收。占用标记的进程已不在时，exec / verify / gate 把那次运行记为 `aborted`（argv 与启动时间取自
`artifacts/<run_id>/start.json`），提示先查输出再重跑，下一次照常执行；reviewer 的标记直接清掉。已验证的 task 不触发 timer：它的下一步属于 reviewer 或 human。

### Independent review boundaries

plan review 的单位是 task：每个 task 只在第一次出现时审一次，一次调用审完所有未审的 task，设计之后再改也不重审；
human 可用 `plan-review --again` 要求重审。记录的身份与准入 guard 见[状态模型](#状态模型)的 task 实例。
reviewer 与 executor 之间的协议：意见分 `must`（不改就方向错、结论错或白跑昂贵实验，须写后果与依据，否则按
`suggest` 记）与 `suggest`（严谨性，executor 可跳过），各最多 3 条，超出的丢弃。`must` 必须由 executor 逐条回应
`applied` 或带事实的 `reject`，init 前检查；带 `human: true` 的 must 须 human 用 `--approve` 选择，`unreviewed` 不认。
task reviewer 写的 successor 与其他 task 一样，在 init 前经独立 plan review：未审时 `init` 先跑 plan review 再复查准入，
仍有未回应的 `must` 或待 human `--approve` 的项即拒绝。plan 已 `approved` 时这条补审只给上一个 task reviewer
指名的 task；其他未审 task 被拒绝，须改回 `proposed`、跑 plan review、经 human 批准再 `init`。
代价是每个新 successor 多一次 plan reviewer 调用。记录只由 plan review 写入（`source="plan_review"` 与它的
`run_id`）；最后一条记录不是 plan review 写的 task 视为未审。
Plan Revision 只承担 human 纠偏。

reviewer 的输入有边界。判据只来自 Goal、`.agent-loop/review-checklist.md` 与设计文档显式链接的检查表；
`archive/` 与 `*-archive.md` 只是历史，可作事实引用，不作判据。证据只来自 prompt 列出的输入、
plan / task / 设计文档直接链接的文件与设计列出的被测代码；缺了就报缺失，不自行搜索。

两个 reviewer 都审被测内容本身，不只审格式与严谨性：交给被测方的题目、数据、样本或请求要有渲染样例，
reviewer 看样例判断它是否在测 Goal 要测的东西；task reviewer 把实际产物与设计不一致归为 `ask_human`。
领域检查项不进 agent-loop，由各 repo 的可选 `.agent-loop/review-checklist.md` 承载，存在时列入两份 prompt。
plan reviewer 另查新增持久状态或读写边界的 task 是否带模块契约、每条不变量是否配了测试，不审代码布局。

task 验证通过后，下一步由 reviewer 提议，worker 不给自己的下一步拍板。init 只要求 task 是 human 批准的
`🔬 doing`，不要求等于 reviewer 的提议。无人值守（`Plan Review: unreviewed`）时只能 init reviewer 指名的 task：
`continue` 的 `next_task`，或 `ask_human` 附带的不受该问题影响的 `next_task`；`stop` 后不能 init，
唯一例外是主线交接：`task.md` 的主线一节为 `Mainline Review: approved`，上一个 task 的 plan 是紧挨 `▶ next`
前的 `✅ done` 行，本次 init 的 plan 是 `▶ next` 行的 plan。plan review 与 `🔬 doing` 检查照旧。
两类调度都由确定性边界触发，不用 LLM 判断是否需要 review：

| 时刻 | 调用 |
|---|---|
| Plan Revision 提交、human 批准前 | reviewer 给 task 准入意见 |
| task 执行、自修、重试 | worker（宿主里的 agent） |
| task verifier 通过且配置了 reviewer | Harness 立即运行 reviewer，经 runner 执行、journal 记账 |
| reviewer 选 `ask_human` / `stop` | human |

reviewer 是项目 `.agent-loop/reviewer.json` 里的一条命令，init 时锁进 config；模型与宿主无关，原则上
强于 worker。`harness verify` 通过后在同一 orchestration 中自动调用 reviewer；决策落盘前，
runner 与下一 task 初始化都被 guard 拒绝。reviewer 只读落盘证据，更新 plan 的结论与下一步、按需写新 task，
并写 `continue | ask_human | stop` 决策，可附不阻塞的 `findings`；标 done、把该 task 的 plan 段搬进
`<plan>-archive.md`、改写指向被移走锚点的链接由 Harness 确定性地完成。worker 只能以事实错误异议一次，
仍分歧即 `ask_human`。
调研见 [`study/multi_agent.md`](docs/study/planning-review/multi_agent.md)。

### Human checkpoints on the phone

配置 `.agent-loop/pager.json` 时，gate 在需要 human 的检查点不让 worker 停下，而是要求 `harness page`：
经 pager CLI 把检查点发到手机，挂着等回复，再把回复映射成 Harness 动作。repo 绑定在 agent-loop 一侧：
task id 形如 `<project>.<task>.<kind>.<utc>`，pager 状态放项目自己的 `.harness/pager-state.json`。

| 检查点 | `OK` | `DO <文字>` | `NO` / `STOP` |
|---|---|---|---|
| `plan_review`：plan 为 proposed | 写 `Plan Review: approved` 并 resume | human 纠偏 | 停 |
| `ask_human`：reviewer 交回 | 采纳 reviewer 提议 | human 纠偏 | 停 |
| `review_failed` / `budget` | 停 | human 纠偏 | 停 |
| `done`：reviewer 选 stop | 只发通知，不等回复 | | |

human 纠偏 = `pause --require-revision`，worker 按 `work-planning` 改 plan 为 proposed，下一次 stop 再发
`plan_review`。`DO` 的文字只作为指令交给 worker，不拼进命令。pager 不能唤醒已退出的 agent：worker 在
检查点挂在 `page` 上等待。

### Adapters

平台事件先经过统一边界，Kernel 和 Policies 不解析原生 payload：

```text
native event → platform codec → HookRequest → adapter core → HookResponse → platform codec
```

`HookRequest` 只使用 `TOOL_USED / COMPACT / STOP` 与 workspace、tool、status、session；`COMPACT`
保留为无副作用的兼容事件，Cursor preCompact 提示由平台 codec 直接处理。
`HookResponse` 只使用 `ALLOW / CONTEXT / CONTINUE`。新增平台只实现两端 codec 和安装配置，
不在共享 core 中增加平台分支。自己的 driver 可以直接发送内部 request，不需要 codec。

CLI `init` 把会话 id（依次取 `AGENT_LOOP_SESSION_ID`、`CURSOR_CONVERSATION_ID`、`DSH_SESSION_ID`）记为 task 的 `owner`。
gate 遇到别的会话拥有的 task 时不写状态、不发 followup；请求不带会话 id 也算别的会话。
没有 owner 的 state 照旧处理。Cursor 会话绑定它读过 `task.md` 的每个项目，stop 与 preCompact 只检查这些项目，
不扫描 workspace 里的其它项目；dsh 会话只看 payload `cwd` 这一个项目，与 CLI 默认 `--root` 一致。
同一会话同一条 followup 只发一次（`adapters/followup.py`），因为 dsh 桥接的 `stop_hook_active` 恒为 false。

宿主与模型解耦：agent-loop 只区分「角色（worker / reviewer）× 宿主（Cursor、dsh、Codex CLI…）」，模型是宿主自己的
provider 配置。同一个 dsh 可以用 DeepSeek 当 worker，也可以用强档模型当 reviewer；换模型不改 agent-loop。

| 宿主 | worker | reviewer | 缺口 |
|---|---|---|---|
| Cursor | enforced（`adapters/cursor/`） | — | — |
| dsh（经 `dsh-hooks-codex` 桥接） | enforced（`adapters/dsh/`） | `reviewer.json` 可指向 dsh headless | memory 只在 `SessionStart` 注入 |
| Codex CLI | portable | 当前默认 reviewer | — |

| Adapter | 职责 |
|---|---|
| `harness/runner.py` | subprocess、process-tree kill、timeout、输出采集 |
| `harness/journal.py` | 有界 artifacts 与 `runs.jsonl` |
| `harness/plan.py` | plan metadata、task revision、pause / resume / Goal Review guard |
| `harness/plan_review.py` | plan reviewer：report 校验与 revision 去重；prompt 在 `harness/prompts/plan_review.md` |
| `harness/review.py` | task 边界 reviewer：执行、决策校验与 follow-up；prompt 在 `harness/prompts/task_review.md` |
| `harness/records.py` | reviewer 决策后把 closed task 移出 active backlog，并保留 archive |
| `harness/fingerprint.py` | 工作树指纹，排除 runtime 与其它 agent 的目录 |
| `harness/page.py` | human 检查点经 pager 发到手机，回复映射成 Harness 动作 |
| `harness/protocol.py` | state / event / transition；不依赖平台 |
| `adapters/protocol.py` | 平台无关的 hook request / response |
| `adapters/core.py` | 子项目发现、memory、Goal Review、completion gate 的事件处理 |
| `adapters/followup.py` | 同一会话的重复 followup 去重 |
| `adapters/cursor/hooks/` | Cursor payload / output codec |
| `adapters/dsh/hooks/` | dsh `hooks-codex` 桥接的 payload / output codec（`Stop`、`SessionStart`） |
| `scripts/sync-to-cursor.ps1` | 安装 user-level adapter |
| `scripts/sync-to-dsh.ps1` | 把 always-apply rules 拼成 `$DSH_HOME/AGENTS.md` |
| `scripts/install-skills.py` | 两个宿主的 skill 链接：agent-loop 自己的 skill 加 `~/.agent-loop/packs.txt` 登记的包，跨来源查重名与 `requires`；不认识任何具体的包 |

`harness/core.py` 只保留兼容 façade 与 orchestration，不再容纳平台 hook 或大段底层实现。

没有 lifecycle hooks 的壳仍可使用 rules、skills 和 Harness，属于 portable mode；只有 adapter
能接收 `STOP` 并回传 `CONTINUE` 时，才属于能强制 completion gate 的 enforced mode。

## Sources of truth

| 内容 | 唯一真相源 |
|---|---|
| 项目的长期事实与结论：行为与接口、测得的结果、约束、带理由的决策、否定发现 | 项目被跟踪的文档（README、设计文档、`docs/`、实验记录） |
| 进行中 Goal 的边界、工作结论与脉络 | plan document |
| active task、`rN`、候选与触发项 | `.agent-loop/task.md` |
| closed task 与旧交接点 | `.agent-loop/archive/`（只按需读取） |
| runtime phase、budget、当前 run | `.harness/state.json` |
| 原始执行证据 | `.harness/runs.jsonl` + `artifacts/`（有界） |
| task 临时文件 | `.harness/tasks/<task_id>/`（task 关闭时删除） |
| 运行环境事实、否决项与指向项目文档的指针 | `.agent-loop/memory/` |
| 会话绑定的项目与已发的 followup | 系统 temp 的 `agent-loop-cursor-sessions/`、`agent-loop-followups/` |
| 共享 memory 的注入记录 | `~/.agent-loop/shared-memory-arrivals.jsonl`（只追加，不参与判定，没有退役规则） |
| 状态与转移是否合法 | `harness/protocol.py` |

plan、task、progress、archive、memory 与 `.harness/` 都不是项目事实的家：它们常被 ignore、不进 upstream，
接手人 clone 项目时拿不到。

`.cursor/task.md` 与 `.cursor/memory/` 只作为旧项目读取兼容，不再写入。`.harness/state.json`
不复制 backlog；memory 不复制 stdout；README 不复制本设计。

## Extension rule

新增需求按顺序判断：

1. 项目差异能否用 config / profile 表达？能就不改代码。
2. 只是某个状态下的做法？放 policy / skill。
3. 只是接一个平台或工具？先映射内部 hook protocol，再放 platform codec。
4. 只有出现新的生命周期状态、事件或不可绕过 guard，才改 Kernel。

每次扩展必须同时删除被替代路径。Kernel contract test 测 transition 与 guard；platform adapter
用原生 payload fixture 测 codec，不复制共享动作测试。

设计文档的写法：

- 只写当前为真的设计；迁移步骤与兼容历史进 CHANGELOG，计划、下一步与实验记录进 plan document。
- 改设计文档的 PR 说出改了哪个设计决定；说不出就不改设计文档。
- 同一节在一个 4 周窗口内第二次补特例时停止追加，改为 RFC 重写该节。

## Public repository contract

- Apache-2.0 是代码、rules、skills 与文档的发行许可证；
- `CONTRIBUTING.md` 与 `AI_POLICY.md` 定义贡献边界，Kernel 变更先走 Issue / RFC；
- `.agent-loop/`、`.harness/` 是 maintainer runtime，不进入发行内容；
- GitHub Issues / Milestones 是公开 backlog，`ROADMAP.md` 只写 Now / Next / Later；
- `SECURITY.md` 与 GitHub Private Vulnerability Reporting 承接 hook、命令执行和日志泄漏问题；
- 支持范围、breaking schema 和迁移方式由 README / CHANGELOG / SemVer 对外声明。

## Repository target

```text
agent-loop/
├── design.md                 # 架构唯一定义
├── README.md                 # 安装、最短使用路径、文档入口
├── rules/agent-loop.mdc      # 最小状态路由 + 不变量
├── harness/
│   ├── protocol.py           # Stable Kernel
│   ├── storage.py            # 原子 JSON / lock
│   ├── runner.py             # subprocess adapter
│   ├── journal.py            # execution evidence
│   ├── plan.py               # Plan Revision / pause gate
│   ├── records.py            # closed-task archive
│   ├── prompts/              # reviewer prompts（Policy 文本）
│   ├── core.py               # orchestration façade
│   └── run.py                # CLI
├── skills/                   # Policies
├── tools/
│   └── pager/                # 独立包：邮件往返；Harness 只经 CLI 调用
├── adapters/
│   ├── protocol.py           # platform-neutral hook boundary
│   ├── core.py               # shared hook actions
│   ├── followup.py           # per-session followup dedupe
│   ├── cursor/hooks/         # Cursor codec
│   └── dsh/hooks/            # dsh (hooks-codex bridge) codec
└── docs/study/               # 按 feature 分目录的调研与设计依据，不承担当前架构定义
```

## Non-goals

- 不做动态 plugin loader；目录和 import 边界足够。
- 不把扁平 task 变成 DAG。
- 不让 Harness 接管未显式交给 runner 的全部 host tool call。
- 不为行数目标删判据；重构只删除重复 owner 与重复路径。
- 与生命周期状态无关的个人工作流 skill / rule 不进发行。

