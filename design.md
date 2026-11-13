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
或授权执行；它没有交给 human 的项时 worker 按意见写 `Plan Review: unreviewed` 开工，有时 human 保留
`approve / revise / stop` 权限（交 human 的判据归 `when-to-stop`）。plan review 按 task 与 Plan Revision 审：task 在它绑定的每个 revision 下审一次；
同一 revision 下新增的 task（含 task reviewer 写的 successor）另审。初始化、resume、pager 与无人值守批准都不能绕过有效记录。task reviewer 继续由 Harness 在 verify
后调用，并只报告会改变 `continue / revise / ask_human / stop` 或下一条命令的问题。
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
| task 实例 | [task 行](#task-row)第二格的 task id，按原字符串匹配；review 只对它审过的 `plan_doc`（规范化的项目相对路径）有效 | 未审 / 已审 / 需重审（任一 `again[].at` 不早于最后一次 review 的 `at`；或 task 行的 `rN` 等于 plan 当前 revision 而最后一次 review 的 `plan_revision` 不同，含没有该字段的旧记录）/ must 未回应 / 待 human 批准（没有不早于该 review 的 `approvals[].at`）；审查失败计数（reviewer 失败时写入，同 plan 与 revision 累加、换了就从 1 起；审查期间输入变更不动它；审查成功删除；stop 门上报后把 `reported` 置真，同一记录不再上报）；`Plan Revision`、task `rN` 与锁定的 `plan_revision` | plan reviewer 写 findings；executor `--respond`；human `--approve` / `--again`；worker 或 human 改 revision | `.harness/plan-review/tasks/<id>.json`；`.harness/plan-review/failed.json`；plan document 头部；`task.md` 的 task 行（已归档时读 `archive/tasks.md`）；`state.json` | `tests/test_plan_review.py` |
| 执行尝试 | 一个 `.harness/` 一次一个 active task；每次运行一个 `run_id` | phase（下表）；`current_run_id` 与 `runner_pid` 表示占用；`verify_attempts` / `wall_seconds_used` 对预算；`verified_fingerprint`；`stop_report_requested` | runner 与 verifier 经 Harness 转移；`disable` | `state.json`；`config.json`（verifier `argv` / `files`（`argv` 指向的工作区内文件的 SHA-256，含被 gitignore 的路径）/ `timeout_seconds` / `expect_regex` / `forbid_regex`、budget、limits，摘要锁在 `config_sha256`）；`artifacts/<run_id>/start.json`；`.harness/lock` | `tests/test_protocol.py`、`tests/test_harness.py`、`tests/test_review.py` |
| 决策权限 | 每个 human 检查点一个 `page.key`；`review_failed` 的 key 含 `review.run_id` | `Plan Review`: `approved` / `unreviewed` / `proposed`；pause（`human` / `goal_review`，`require_revision`）；`review.attempts`（异议一次）；`review.report_requested`（reviewer 失败只报一次） | human 经 Gate、`pause`、pager 回复；按 reviewer 开工只能写 `unreviewed`；init 锁定 reviewer 与 pager 命令 | plan document 头部；`.harness/pause.json`；`state.json` 的 `review` / `page`；`.harness/pager-state.json`；`config.json` 的 `reviewer` / `pager` | `tests/test_harness_pause.py`、`tests/test_page.py` |
| 调度 | 决策的 `verify_run_id` 等于 `last_run_id` 才算本次已审 | `continue` / `revise` / `ask_human` / `stop` 与 `next_task`；task 行 `🔬 doing`；主线 `▶ next` / `✅ done` 与 `Mainline Review`；Goal attention 到期（`actions_since_goal_review` 达到 `after_actions`，或距 `last_goal_review_at`、没有时距 `created_at` 的秒数达到 `after_seconds`） | task reviewer 写决策，Harness 校验后落盘；human 与 worker 改 `task.md`；runner 累加计数 | `state.json` 的 `review`；`.harness/review/decision.json`；`task.md` 的 task 表与 `## 主线`；`config.json` 的 `goal_review` | `tests/test_review.py`、`tests/test_attention.py` |
| 会话归属 | 会话 id，依次取 `AGENT_LOOP_SESSION_ID`、`CURSOR_CONVERSATION_ID`、`DSH_SESSION_ID` | `owner` 等于请求的会话、属于别的会话或为空；Cursor 会话绑定的项目；followup 已发 | init 写 `owner`；Cursor hook 读 `task.md` 时绑定它所在的项目，项目是自带 `.git` 的目录，或 workspace 内没有上级目录含 `.agent-loop/task.md` 的目录（测试 fixture 与示例因此属于外层项目）；completion gate 写 followup 标记 | `state.json` 的 `owner`；系统 temp 的 `agent-loop-cursor-sessions/<sha256>`、`agent-loop-followups/<sha256>` | `tests/test_harness_stop.py`、`tests/test_cursor_session_scope.py` |
| 记录寿命 | closed task 按 task id 归档；`init` 只接受 CLOSE 能归档的设计位置（见 [One plan document](#one-plan-document)）；`.agent-loop/` 的其余文件按名字里的已关闭 task id 或所在的已关闭 Goal plan 目录认领 | active / `✅ done` / `❌ dropped`；task 设计段在 plan 中或在 `<plan>-archive.md`；scratch 存在或已删；`progress.md` 的交接段数；[`leftovers`](#leftovers)（认领到已关闭记录、没被现行文档提到、也不受保护的文件，只报不删）；journal 与 artifacts 条数 | Harness CLOSE（reviewer 决策落盘后，或 `clean-task`）移走第一段以外的交接段；worker 处理 `leftovers`；runner 按 `limits` 裁剪 | `task.md` → `archive/tasks.md`；plan → `<plan>-archive.md`；`progress.md` → `archive/progress-YYYY-MM.md`；`.harness/tasks/<id>/`；`runs.jsonl`、`artifacts/` | `tests/test_records.py`、`tests/test_scratch.py`、`tests/test_review.py` |

<a id="task-row"></a>
task 行按读它的操作定义，主线表的行只有五格，不属于任何一种：

- 身份（`harness/records.py` 的 `_task_id`）：`task.md` 或 `archive/tasks.md` 里至少七格、首格完整匹配 `P\d+`、
  第二格非空且小写不是 `id` 的表格行；第二格是 task id。`open_task_ids`、`task_row`、`archived_task_ids` 与归档按它找行。
- 关闭（`_closed`）：任一格以 `✅ done` 或 `❌ dropped` 开头的 task 行。`open_task_ids` 是 `task.md` 里没关闭的 task 行，
  归档移走关闭的。
- revision（`harness/plan.py` 的 `task_plan_revision`）：依次在 `task.md`、`archive/tasks.md` 里找至少七格、第二格等于
  task id 的第一行，第三格须是 `rN`。

契约测试：`test_records.py` 的 `test_only_rows_led_by_a_priority_are_task_rows`。

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

<a id="guards"></a>
跨维度的 guard 是可执行条件，不写成 agent 自觉。每道 guard 只在「拦哪些操作」列出的操作上检查，列出的操作各自写明
不满足时的结果。gate 指 stop hook 调用的 `completion_gate`；exec 与 verify 都经 `core.run_command`。gate 的 plan 检查
（`plan_can_run`）在 task 已是本次已审、verifier 未变的 `VERIFIED` 时不运行，这时 gate 直接交接 reviewer 的决定。

| guard | 拦哪些操作 | 执行它的函数 | 契约测试 |
|---|---|---|---|
| revision 一致 | init：plan `Plan Revision` ≠ task `rN` 时拒绝；exec、verify、gate 的 plan 检查、Goal Review `--decision continue`：plan `Plan Revision` 须等于 `state.plan_revision`（不等时 exec / verify / gate 写 `require_revision` 的 pause），也须等于 task `rN`（不等时写普通 pause），continue 不满足即拒绝；resume：plan `Plan Revision` ≠ task `rN` 时拒绝，通过后把它写进 `state.plan_revision` | `core.initialize`；`plan.plan_can_run`（经 `run_command`、`completion_gate`、`attention.record_goal_review`）；`plan.resume` | `test_harness_pause.py`：`test_init_rejects_task_bound_to_another_revision`、`test_human_correction_requires_new_approved_revision` |
| 纠偏要求新 revision：pause 带 `require_revision` 时，`Plan Revision` 大于 `state.plan_revision` | resume、Goal Review `--decision continue`：拒绝；下一 task 的 init：未消费的 `require_revision` 请求、本次 `plan_doc` 与上一个 task 是同一文件且其 `Plan Revision` 大于上一个 state 的 `plan_revision` 时，视同 human 批准，不再要求等于 `next_task`、`stop` 后也可 init；不满足时无人值守守卫照旧。init 写入新 config / state 后删请求，任何拒绝都保留 | `plan.resume`；`attention.record_goal_review`；`plan.has_revised_plan_pause`（经 `core.initialize`） | `test_harness_pause.py`：`test_human_correction_requires_new_approved_revision`；init 放行的回归测试在 #203 的提交 `586ecfe` |
| `Plan Review` 是 `approved` 或 `unreviewed` | init：`proposed` 时以 `PAUSED` 起步并写 pause；exec、verify、gate 的 plan 检查：写 pause；resume、Goal Review `--decision continue`：拒绝 | `core.initialize`；`plan.plan_can_run`（同上）；`plan.resume` | `test_harness_pause.py`：`test_proposed_plan_starts_paused`；`test_page.py`：`test_proposed_plan_is_paged_and_ok_approves_and_resumes` |
| 同一 plan 的 `Plan Revision` 只在有来源时递增：来源是带 `require_revision` 的 pause 请求，只由 `pause --require-revision`（human 纠偏，task 已关闭或已 disable 也可写）与 Goal Review `replan` 写入；exec、verify、gate 因 revision 变化自动写的 pause 不带它 | init（与上一个 task 的 state 比）、resume（与当前 state 比）：revision 增大而无来源时拒绝并保留 pause；接受时把 from / to / reason 写进 state 的 `revision_source`，与新 `plan_revision` 同一次写入，未升版的后继沿用 | `plan.revision_source`（经 `core.initialize`、`plan.resume`） | `test_harness_pause.py`：`test_a_revision_bump_without_a_source_is_refused`、`test_a_goal_review_replan_is_a_source`、`test_a_successor_without_a_bump_keeps_the_source`、`test_human_correction_requires_new_approved_revision` |
| task 有有效的 plan review（配置了 reviewer 且绑定 plan 时）：最后一条记录对应当前 `plan_doc`（没有 `plan_doc` 字段的记录算对应）、`source` 不是 `task_review`、之后没有 `--again`；`must` 全部回应；有 human 项时有不早于该 review 的 `--approve` | init：未满足且 `Plan Review` 是 `approved`、task 不是 reviewer 选的后继时拒绝，要求先改回 `proposed`；其余情况当场跑 plan reviewer 再判，仍不满足即拒绝；exec、verify：写 pause；resume：未满足时当场跑 plan reviewer，仍不满足即拒绝，满足了而 `Plan Review` 是 `approved` 时改回 `proposed` 并拒绝。init 与 resume 还要求有 human 项时 `Plan Review` 不是 `unreviewed` | `plan_review.plan_review_ready`（经 `core.initialize`、`run_command`、`plan.resume`） | `test_plan_review.py`：`test_must_items_need_an_answer_before_init`、`test_human_items_wait_for_the_human`、`test_approved_plan_cannot_skip_missing_review`、`test_proposed_plan_is_reviewed_before_human_resume`、`test_task_id_reused_by_another_plan_is_reviewed_again`、`test_records_from_before_the_protocol_are_reviewed_once_more`、`test_a_new_revision_reviews_the_tasks_bound_to_it`、`test_a_revision_bumped_during_the_review_records_nothing`；`test_review.py`：`test_successor_is_plan_reviewed_before_init` |
| 没有 pause request（`.harness/pause.json`） | exec、verify：拒绝并转 `PAUSED`；运行中的命令：runner 轮询到即中断；task review：拒绝；gate：只发 Goal Review 提示、pager followup，或（未配 pager、配了 reviewer 且 plan 是 `proposed` 时）plan review 门：审查在跑 → 等待，有 task 未审或需重审 → plan-review 命令（同 revision 失败满 2 次时改为上报一次后放行），agent 可答的 must 未回应 → `--respond` 命令，只剩 human 项 → 放行；门消息带 `STOP_GATE_PREFIX`，adapter 不按重复消息吞掉 | `plan.pause_request`（经 `run_command`、`runner.execute_process`、`review.run_review`、`completion_gate`）；`plan_review.stop_followup` | `test_harness_pause.py`：`test_pause_interrupts_a_running_process`；`test_plan_review.py`：`StopGateTest` |
| 被 pause 或 resume 的 task 仍开着（`state.plan_revision` 非空时）：task id 在 `records.open_task_ids` 里 | 不带 `require_revision` 的 pause 写入（`pause` CLI、init 的 proposed 暂停、Goal attention、exec / verify 因 plan 或 review 未就绪的暂停）：拒绝；resume（当前 pause 不带 `require_revision` 时）：调 plan reviewer 前与持锁后各查一次，拒绝并提示 init 后继 | `plan._task_eligibility_error`（经 `plan.request_pause`、`plan.resume`） | `test_harness_pause.py`：`test_pause_and_resume_refuse_a_closed_task` |
| config 未变：`config.json` 的摘要 = `state.config_sha256` | 每个经 `load_runtime` 读运行时的操作（exec、verify、task review、resume、`status`）：拒绝；gate：要求先修复 state | `storage.load_runtime` | `test_harness.py`：`test_config_drift_is_rejected` |
| 预算有余额：`verify_attempts` < `max_attempts`，且 `wall_seconds_used` < `max_wall_seconds` | exec、verify 开跑前：拒绝并转 `STOPPED`，单次运行的 timeout 截到剩余 wall；exec 结束与未通过的 verify 结束：用尽即转 `STOPPED`；通过的 verify 转 `VERIFIED`，被 pause 中断的运行转 `PAUSED`，两者都不查预算；gate：`STOPPED` 时第一次要求 Auto-Stop Report 并记 `stop_report_requested`，记过之后只发 followup | `core._budget_exhausted`（经 `run_command`）；`core.completion_gate` | `test_harness.py`：`test_timeout_kills_run_and_stops_at_budget`、`test_completion_gate_requests_one_stop_report` |
| task reviewer 的决定已落盘（配置了 reviewer 且 phase 为 `VERIFIED` 时）：`review.verify_run_id` = `last_run_id` 且有 `decision` | exec、verify：未落盘、`continue`、`ask_human`、`stop` 都拒绝，`revise` 放行；下一 task 的 init：reviewer 正在跑、未落盘或 `revise` 时拒绝；`clean-task`：未落盘或 `revise` 时拒绝 | `core.run_command`；`core.initialize`；`core.clean_scratch` | `test_review.py`：`test_pending_review_blocks_execution_and_next_task`、`test_other_decisions_still_block_execution`、`test_revise_keeps_the_task_open_until_it_is_verified_again` |
| verifier 文件未变：`verifier.files` 的每个摘要 = init 时的值（见 [verifier 文件锁](#verifier-file-lock)） | verify：开跑前拒绝，写通过前判 `reject`；task review：这次 verify 的决定未落盘时拒绝；gate：决定未落盘时比对，不符判 stale | `fingerprint.verifier_drift`（经 `run_command`、`review.run_review`、`completion_gate`） | `test_harness.py`：`test_verifier_file_edit_before_verify_is_refused`、`test_verifier_that_rewrites_itself_does_not_pass`、`test_verifier_file_edit_after_verify_makes_evidence_stale`；`test_review.py`：`test_review_refuses_a_changed_verifier`、`test_gate_rechecks_the_verifier_after_an_invalid_review` |
| evidence 新鲜：verifier 退出码为 0 且输出符合 `expect_regex` / `forbid_regex`，之后 workspace fingerprint = `verified_fingerprint` | verify：不符合输出约定判 `reject`；task review：这次 verify 还没审时，fingerprint 不符拒绝；gate：`VERIFIED` 且这次 verify 还没审时，fingerprint 不符转 `FAILED`（`EVIDENCE_STALE`）。「已审」只看 `review.verify_run_id` = `last_run_id`：无效的 reviewer 可能已改写 `task.md`，那是允许的工作文档改写 | `core._matches_contract`；`fingerprint.workspace_fingerprint`（经 `run_command`、`review.run_review`、`completion_gate`） | `test_harness.py`：`test_output_contract_can_reject_exit_zero`、`test_completion_gate_requires_fresh_verification`、`test_git_path_skips_nested_foreign_runtime` |
| 请求的会话是 `owner`，或 `owner` 为空 | gate：不是时不写状态、不发 followup | `core.owned_by_other`（经 `completion_gate`） | `test_harness_stop.py`：`test_other_sessions_task_is_left_alone` |
| task id 独占 plan-review 记录：`.harness/plan-review/tasks/<id>.json` 里的 `task_id` 等于请求的 id（大小写不同的 id 在不分大小写的文件系统上共享一个文件） | init 的 plan review、`plan-review` 及其 `--respond` / `--approve` / `--again`：拒绝且不改记录；task reviewer 指名后继：决定作废 | `plan_review.task_record`（经 `run_plan_review`、`plan_review_ready`、`respond_task`、`approve_task`、`again_task`、`review.run_review`） | `test_plan_review.py`：`test_a_record_of_another_task_id_is_refused_everywhere`；`test_review.py`：`test_successor_sharing_another_tasks_record_is_refused` |
| 后继是开着的 task：decision 的 `next_task` 在 `task.md` 有 task 行，其第六格非空且不包含 `✅ done` 或 `❌ dropped` | task reviewer 指名后继：决定作废 | `review.run_review` | `test_review.py`：`test_successor_must_be_an_open_task` |

workspace fingerprint 由 `harness/fingerprint.py` 的 `workspace_fingerprint` 计算，两种项目各有范围：

- git 项目且已有提交：`HEAD`、相对 `HEAD` 的 diff（含已跟踪的文件）与未被忽略的未跟踪文件，不含 `.harness/` 与其他 agent
  的运行目录（`.codex/`）。`init` 把 `/.agent-loop/`、`/.harness/` 写进 `.git/info/exclude`，所以 CLOSE 改未跟踪的
  `.agent-loop/` 文件不改 fingerprint；已被 git 跟踪的 `.agent-loop/` 文件计入 diff。
- 不是 git 仓库或还没有提交：`.harness/`、`.git` 与其他 agent 的运行目录之外全部文件的哈希，CLOSE 改 `task.md` 也改 fingerprint。

<a id="verifier-file-lock"></a>
verifier 文件锁由 `harness/fingerprint.py` 拥有，与 workspace fingerprint 分开：

- `verifier_files(root, argv, evidence_files=None)`：`argv` 中按 root 解析后落在 root 内、未声明为 evidence 的普通文件，
  返回相对 root 的 POSIX 路径到 SHA-256 的映射；
  `init` 写进 `verifier.files`，由 `config_sha256` 锁住。不追踪 verifier import 的模块与 root 外的文件。
- `init --evidence-file PATH` 可重复：显式声明 task 产出、verifier 读取的文件，不写进 `verifier.files`；
  新鲜度仍按上述 workspace fingerprint 的范围检查。PATH 与 verifier 参数都按 root 解析，必须对应同一个文件路径，
  文件可以尚不存在；不匹配或指向目录时 `init` 拒绝，不写 state / config。未声明的文件照旧上锁，
  不按后缀、参数位置或是否被写过推断。verify 因文件变化拒绝时，提示 task 产出应在重新 init 时用 `--evidence-file` 声明。
- `verifier_drift(root, config)`：逐个比对 `verifier.files` 的键，返回第一个缺失、不可读或摘要不符的路径，全部相符时返回 None；
  config 没有 `files` 时比对集合为空。
- task review 与 gate 的比对期从 `init` 到 task reviewer 对这次 verify 的有效决定落盘，之后的 `--objection` 不复核。
  `continue` / `ask_human` / `stop` 落盘的同一步关闭 task 并删除 `.harness/tasks/<id>/`；`revise` 保留 task 与 scratch，
  下一次 verify 开跑前比对。reviewer 写出无效决定不结束比对期，`completion_gate` 继续复核。
- 每次 verify 在开跑前与判定通过前各比对一次：运行中改了 verifier 又在退出前改回原内容，不会被发现。

<a id="leftovers"></a>
`.agent-loop/` 的退役由 `harness/records.py` 拥有，在 task CLOSE 的同一步运行（reviewer 决定落盘、`close_task` 之后，
或 `clean-task`）：

- `archive_progress(root)`：`progress.md` 只留第一个 `## ` 段与段前的前言（新交接写在顶部），其余段按原文行区间追加到
  `archive/progress-YYYY-MM.md`（CLOSE 时刻的月份）。先写 archive 再原子替换 `progress.md`；任一步失败返回错误，并入
  `cleanup_error` / `clean-task` 的 `error`，`progress.md` 保持原样、task 照常关闭。archive 已追加而 `progress.md` 未替换时，
  重跑按段内容去重，不重复追加。围栏代码块里的 `## ` 不算段首。
- `leftovers(root)`：无状态，每次调用重算，只报不删。报出的文件同时满足三条：认领到已关闭记录、没被现行文档提到、不受保护。
  - 认领：文件名（不含扩展名，不分大小写）含已关闭 task id，id 前不是字母、后不是字母数字（`verify_2cache-format` 认领
    `cache-format`，`verify_cache-formats` 不认领 `cache-format`）；或它最近的 plan 目录属于主线表里 `✅ done` 的 Goal。已关闭 task id 是 `archive/tasks.md`
    的 id 减去 `task.md` 仍开着的 id，因为 id 跨 Goal 复用。plan 所在目录须是 `.agent-loop/` 的子目录，或项目根之内、
    `.agent-loop/` 之外的目录（不是项目根本身）；直接放在 `.agent-loop/` 下或项目根的 plan 不认领任何文件。
    `.agent-loop/` 之外的目录只认领 `✅ done` Goal 的，候选只取 `git ls-files --others`（未跟踪，含被忽略；`.git/`、
    `.harness/` 下的除外），被跟踪文件是项目自己的；项目不是 git 仓库、没有提交或 git 失败时不认领这类目录。报出路径相对项目根。
  - 现行文档：`task.md`、`progress.md` 第一段、`memory/*.md`、`.agent-loop/*.json`、未完成主线行与 `task.md` 里至少六格、
    未关闭的表格行链接的 plan。「提到」是文件名或 `.agent-loop/` 相对路径原样出现：引用多数写成反引号里的文件名，不是链接。已关闭 Goal 的
    plan、`*-archive.md` 与 `archive/` 是历史，其中的提及不算。
  - 受保护：`.agent-loop/` 顶层的 `task.md`、`progress.md`、`memory/`、`archive/`、`reviewer.json`、`pager.json`、
    `review-checklist.md`、`reports/`（各有自己的退役规则，不参与扫描）；主线行与上述未关闭表格行链接的 plan 文档、
    未完成 Goal 的 `*-archive.md` 与 `sub-exp/`（`✅ done` Goal 冻结后 plan 目录只留 plan document），任意 `archive/` 下的文件；active Harness 的 config 锁定的 verifier 文件（删掉它会让
    completion gate 判证据 stale）。锁定集合经 `harness.storage.load_runtime` 读：没有 `.harness/state.json` 或 Harness
    不 active 时为空；读不出或 `config_sha256` 不符时锁定集合未知，`leftovers` 返回空列表。`status` 先 `load_runtime`
    再调用它，state 损坏时 `status` 失败。
  - 目录合并只统计扫描集合里的文件：一个目录的扫描文件全部被报出时合并为该目录一行；顶层以外的受保护文件计入总数、
    不计入报出数。`.agent-loop/` 之外的目录把被跟踪文件也计入总数，所以含被跟踪文件的目录不合并，只报其中的未跟踪文件。每个条目按满足条件的最高祖先目录合并。
- 只报不删、不进 completion gate：Harness 分不清长期工具与一次性脚本，报出的条目挡不住完成。认领只看名字与 plan 目录：
  按名字之外的线索认领会把没写进文档的长期工具也报出来，所以不带已关闭标识的条目（例如迁到别的工作副本的支线目录）不报。

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
设计（策略、手写的产出样例、关键选择、不做什么、验收怎么判）
当前结论
脉络（一个阶段一行：回答同一个问题的一段 task，或一次 Plan Revision；不放读数与链接）
---  以下是执行细节：human 在 Gate 只读上面几节
系统 / Pipeline（确实存在才写）
<task id> 标题段（task 设计）
Experiment Log
```

单个实验直接追加到 `Experiment Log`。只有同一 Goal 下出现多个独立实验、详细日志开始遮蔽稳定头部、
或需要并行维护时，才拆 linked `sub-exp/<id>.md`；plan document 始终保留结论与链接。
Harness 参数叫 `plan_doc`，不关心文件名是 feature、exp 还是其它名字。

task CLOSE 时，Experiment Log 的多轮记录合并成 task 结论并入脉络的当前阶段行，换方向时开新行；读数、链接与
已收口内容进入 linked archive，不继续占用活跃表。脉络由做决定的一方当场写，CLOSE、replan 与冻结都保留。Goal CLOSE / pivot 时冻结 plan 为 as-built。task CLOSE 不删 sub-exp，只按 evidence 指针读取；主线行改 `✅ done` 时 archive 与 sub-exp 的关键点并进头部后删除，冻结后 plan 目录只剩 plan document（条款归 `work-planning` 的主线交接）；
run 输出的位置与删除时机见 `experiment-design` 的 CLOSE self-audit。closed task 与旧交接快照同样移出活跃
`.agent-loop/task.md` / `progress.md`；`disproved / rejected` 因仍会阻止重复试错而保留在 memory。

CLOSE 只把以 task id 开头的标题段（连同标题前的 `<a id>`）移进 `<plan>-archive.md`，所以 `init --plan-doc` 在准入时
检查 task 设计的位置：task 行里的本地链接相对 `task.md` 解析；指向 plan 的链接必须全部落在这类标题段内（按标题的
GitHub slug 或段首 `<a id>` 匹配），且至少一个链接合格；plan 目录内已存在的独立文件（如 `sub-exp/<id>.md`）也合格，
它不删，CLOSE 不搬。主题标题、共用标题、不带 anchor 的 plan 链接与 plan 目录外的文件（含 `.harness/tasks/<id>/`）
都不合格。slug 与 GitHub 不一致（如重复标题的 `-1` 后缀）时表现为误拒，修法是在 task 标题前加 `<a id>`，guard 不猜。
旧 plan 里已写在主题标题下的设计不会被追溯迁移；它们的 task 再次 `init` 前须按上述位置改写。

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

plan review 的单位是 task 与 Plan Revision：task 在它绑定的每个 revision 下审一次，一次调用审完链接到本 plan
（或其目录内已有文件）、未关闭且未审或需重审的 task；同一 revision 内改设计不重审，暂留旧 `rN` 的 task 不重审。
记录写 reviewer 启动时的 revision，reviewer 返回时 revision 或 task 绑定已变就不写记录，也不动失败计数：
这一判定先于「reviewer 失败 / 改了工作区」，因为 workspace fingerprint 同样看得到这些编辑。做法同乐观并发控制的版本
校验（如 HTTP `If-Match` 不符返回 412）：输入过期要求重来，不算执行失败。
最后一次 review、未回应的 `must`（按是否交 human 分组）与正在跑的审查只由 `harness/plan_review.py` 的
`last_review` / `open_musts` / `running_review` 读取，准入、启动与 stop 门共用，各自只定出口；哪些表格行是 task 行见[状态模型](#task-row)。
human 可用 `plan-review --again` 要求重审。记录的身份与准入 guard 见[状态模型](#guards)。
reviewer 与 executor 之间的协议：意见分 `must`（不改就方向错、结论错或白跑昂贵实验，须写后果与依据，否则按
`suggest` 记）与 `suggest`（严谨性，executor 可跳过），各最多 3 条，超出的丢弃。`must` 必须由 executor 逐条回应
`applied` 或带事实的 `reject`，init 前检查；带 `human: true` 的 must 须 human 用 `--approve` 选择，`unreviewed` 不认。
task reviewer 写的 successor 与其他 task 一样，在 init 前经独立 plan review：未审时 `init` 先跑 plan review 再复查准入，
仍有未回应的 `must` 或待 human `--approve` 的项即拒绝。plan 已 `approved` 时这条补审只给上一个 task reviewer
指名的 task；其他未审 task 被拒绝，须改回 `proposed`、跑 plan review、经 human 批准再 `init`。
代价是每个新 successor 多一次 plan reviewer 调用。task reviewer 指名的 successor 若与别的 task 共用记录文件（大小写撞名），
决策在落盘前作废，免得无人值守时绑到一个 `init` 会拒绝的 task。记录只由 plan review 写入（`source="plan_review"` 与它的
`run_id`）；最后一条记录不是 plan review 写的 task 视为未审。
Plan Revision 只承担 human 纠偏。

reviewer 的输入有边界。判据只来自 Goal、`.agent-loop/review-checklist.md` 与设计文档显式链接的检查表；
`archive/` 与 `*-archive.md` 只是历史，可作事实引用，不作判据。证据只来自 prompt 列出的输入、
plan / task / 设计文档直接链接的文件与设计列出的被测代码；缺了就报缺失，不自行搜索。

两个 reviewer 都审被测内容本身，不只审格式与严谨性：交给被测方的题目、数据、样本或请求要有渲染样例，
reviewer 看样例判断它是否在测 Goal 要测的东西；实际产物与设计不一致时，修法明确的由 task reviewer 写修正 task 并选
`continue`，修正还是换方向要 human 取舍时才选 `ask_human`。
领域检查项不进 agent-loop，由各 repo 的可选 `.agent-loop/review-checklist.md` 承载，存在时列入两份 prompt。
plan reviewer 另查新增持久状态或读写边界的 task 是否带模块契约、每条不变量是否配了测试，不审代码布局。

task 验证通过后，下一步由 reviewer 提议，worker 不给自己的下一步拍板。init 只要求 task 是 human 批准的
`🔬 doing`，不要求等于 reviewer 的提议。未经 human 批准（`Plan Review: unreviewed`）时只能 init reviewer 指名的 task：
`continue` 的 `next_task`，或 `ask_human` 附带的不受该问题影响的 `next_task`；`stop` 后不能 init。
两个例外：主线交接，即 `task.md` 的主线一节为 `Mainline Review: approved`，上一个 task 的 plan 是紧挨 `▶ next`
前的 `✅ done` 行，本次 init 的 plan 是 `▶ next` 行的 plan；human 纠偏，即有未消费的 `pause --require-revision`
请求，且同一份 plan 的 revision 已高于上一个 task 的（判定见上表「纠偏要求新 revision」）。plan review 与 `🔬 doing` 检查照旧。
纠偏后的新 task 只经 init 开工，`resume` 不切换 task。init 不持状态锁，纠偏判定只读 `.harness/pause.json` 与 plan，
不新增写者；与 init 并发的 `pause` 不在保证内。
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
并写 `continue | revise | ask_human | stop` 决策，可附不阻塞的 `findings`；标 done、把该 task 的 plan 段搬进
`<plan>-archive.md`、改写指向被移走锚点的链接由 Harness 确定性地完成。worker 只能以事实错误异议一次，
仍分歧即 `ask_human`。
`revise` 把漏了收口的 task 退回给它自己：Harness 不关闭、不清理 scratch，只放行 runner 与 verify，期间拒绝
init 与 `clean-task`；重跑 verify 后自动再审。每个 task 只能退回一次：review 记录的 `revised_run` 记住被退回的
verify run，跨 review 与 verify 保留，init 时清空。更晚的 verify 的 task review prompt 会说明 `revise` 已用掉，
本次只能选 `continue` / `ask_human` / `stop`；首次审查与同一 verify 的异议重审不加此说明。
同一 verify 的异议重审仍可选 `revise`；更晚的 verify 再选 `revise`
时本轮没有有效决策（不沿用上一轮的决策，它属于上一次 verify），按无效 review 重审，`MAX_REVIEWS` 次后交 human。
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
保留为无副作用的兼容事件，Cursor preCompact 的提示与会话压缩标记由平台 codec 直接处理。
`HookResponse` 只使用 `ALLOW / CONTEXT / CONTINUE`。新增平台只实现两端 codec 和安装配置，
不在共享 core 中增加平台分支。自己的 driver 可以直接发送内部 request，不需要 codec。

CLI `init` 把会话 id（依次取 `AGENT_LOOP_SESSION_ID`、`CURSOR_CONVERSATION_ID`、`DSH_SESSION_ID`）记为 task 的 `owner`。
gate 遇到别的会话拥有的 task 时不写状态、不发 followup；请求不带会话 id 也算别的会话。
换会话只发生在 task 关闭之后：从 `init` 到 task 关闭保持同一 worker 会话，验证与已配置 reviewer 的决策落盘也在此周期内；
没配 reviewer 时，验证通过后 CLOSE 跑完 `clean-task` 与 `disable` 即关闭；`revise`、pause、预算停止与未验证通过就
`disable` 不关闭 task，修复或恢复留在原会话。关闭后换不换按 `task-state` 的判据，
换了的话下一个 task 由新会话 `init`，写入新 `owner`，接续靠 `.agent-loop/progress.md` 的交接笔记。
stop 把交接方式传给 gate：环境变量 `AGENT_LOOP_SESSION_HOST` 非空时为 `host`（关闭后写交接并结束这一轮，由宿主判），
否则本会话收到过 preCompact 时为 `new_session`（请 human 开新会话；压缩时窗口小于 1M 则为 `new_session_1m`，
另请 human 给新会话选 1M 模型），都不是时 followup 照旧。agent 可能在 stop 之前
就按 reviewer 的 `continue` 或 CLOSE 开下一个 task，所以 `verify` 通过时按同样的选择在输出里带同一条 `handoff`。preCompact 对每个带 id 的会话
记标记与窗口大小（`harness/compaction.py`），首次压缩且窗口小于 1M 时提示切 1M 模型，都不看是否有 Harness。这条约束由规则、宿主与调度工具遵守，Harness 不加会话切换的 guard。
没有 owner 的 state 照旧处理。Cursor 会话绑定它读过 `task.md` 的每个项目，stop 与 preCompact 只检查这些项目，
不扫描 workspace 里的其它项目；dsh 会话只看 payload `cwd` 这一个项目，与 CLI 默认 `--root` 一致。
<a id="session-scope"></a>
绑定归 `adapters/cursor/session_scope.py`：被读的 `<dir>/.agent-loop/task.md`（或旧 `.cursor/task.md`）让 `<dir>` 成为候选，
`<dir>` 须在 workspace 内。候选自身没有 `.git`（目录，或 worktree / submodule 的文件），且它与 workspace 根之间（含根）
有目录自己的 `task.md` 存在时，它是那个项目的数据（测试 fixture、示例），不绑定；scope 文件里已有的这类条目也不再返回。
有 `.git` 的嵌套目录照旧绑定：clone 在项目里的仓库是独立项目，只按嵌套跳过会让它的门禁静默失效。
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
| `adapters/codex_review.py` | Codex CLI reviewer 入口（Windows 经 WSL）：`reviewer.json` 不写路径，Codex 参数取 `AGENT_LOOP_CODEX_ARGS` |
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
| 只证明 task 通过的验收证据：验证读数、合并上线与首次使用记录、观察窗口的计数 | plan document 的 Experiment Log（随它进 archive） |
| active task、`rN`、候选与触发项 | `.agent-loop/task.md` |
| closed task 与旧交接点 | `.agent-loop/archive/`（只按需读取） |
| runtime phase、budget、当前 run | `.harness/state.json` |
| 原始执行证据 | `.harness/runs.jsonl` + `artifacts/`（有界） |
| task 临时文件 | `.harness/tasks/<task_id>/`（task 关闭时删除） |
| 运行环境事实、否决项与指向项目文档的指针 | git 目录下的 `agent-loop/memory/`，同一 clone 的工作树共用；不是 git 仓库时为 `.agent-loop/memory/` |
| 会话绑定的项目与已发的 followup | 系统 temp 的 `agent-loop-cursor-sessions/`、`agent-loop-followups/` |
| 状态与转移是否合法 | `harness/protocol.py` |

plan、task、progress、archive、memory 与 `.harness/` 都不是项目事实的家：`init` 与 `plan-review` 把 `/.agent-loop/`、
`/.harness/` 写进 `.git/info/exclude`，它们默认不进版本库，接手人 clone 项目时拿不到。已跟踪的文件照旧跟踪；
要版本化新的 agent 状态时用 `git add -f`。

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
- 同一节在一个 4 周周期内第二次补特例时停止追加，改为 RFC 重写该节。

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
│   ├── codex_review.py       # Codex CLI reviewer entry point
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

