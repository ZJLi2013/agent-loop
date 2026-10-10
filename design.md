# agent-loop Design

Plan Revision: 15
Plan Review: approved

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
或授权执行；human 保留 `approve / revise / stop` 权限。每个 plan identity + revision 只审一次，
初始化、resume、pager 与无人值守批准都不能绕过有效记录。task reviewer 继续由 Harness 在 verify
后调用，并只报告会改变 `continue / ask_human / stop` 或下一条命令的问题。
固定时间与文件修改 review 不采用——它们没有稳定的决策边界。
Codex、Cursor 等宿主的会话与缓存目录不属于项目状态，也不进入 agent-loop 的生命周期。

## 下一步决策

Pager 已增加 Feishu 长连接 transport adapter，未改 Harness、pager `Transport` 契约或 lifecycle。
SDK WebSocket 接收消息并入队，普通文本映射为 `DO`，同时保留 `OK / NO / STOP / DO`；
发送方和 chat 均使用 allowlist，凭据只从本机环境变量读取。同一 transport 只允许一个
pending task，避免自然文本被错误关联。CardKit 逐 token 输出不进入首版。

⚠️ 真实 Feishu app 凭据、权限和 chat / sender ID 尚未提供，
端到端消息收发需在这些本机配置就绪后验证。

r14（human 2026-10-06 批准）：closed-task 归档按 task id 去重，跨 Goal 重用 id 时新行既离开
active 又不进 archive。t34 已改为按整行去重，未引入新状态或配置。

r15（human 2026-10-06 批准）：研究型实验的方向与方案只靠模型推理，设计前不查领域先例，
否定结果后也不对照业界已有解法。t35 已把两次调研挂到现有挂点：`experiment-design` 的设计模板
与结果写回，以及两个 reviewer 的检查项；未新增 state、skill 或文件。当前没有后续实现 task。

## Experiment Log

| Exp | 假设 | 状态 | 关键结果 | 结论 / evidence |
|---|---|---|---|---|
| t9-e1 | CLOSE 时改变记录生命周期，可以缩小新 session 的默认上下文且不损失追溯 | promoted | agent-loop 的 active `task.md` 估算字符数 2,347 → 1,198（−49%），4 条 closed 明细仍可从 archive 读取；reviewer / pager / revision guard 集成问题已修复；core 56 + pager 37 tests 通过 | 假设成立；[案例](case_study/agent-loop-record-growth.md) |
| t27-e1 | 把 self-audit 绑定现有 CLOSE，足以清理 task 内过程内容而无需新 gate | promoted | 回读完整 diff 后只剩 7 个持久 Policy / 入口文档，无未跟踪文件或临时脚本；重复实现说明归并到 `experiment-design`；core 56 + pager 37 tests 通过 | 假设成立：保持纯 Policy |
| t28-e1 | 收紧现有 reviewer Policy 足以阻止微步骤重审，无需扩展 Kernel | superseded by t30 | prompt 契约测试与 core 56 tests 通过；schema、CLI、状态机未变 | task 边界能抑制微步骤重审，但不能在投入资源前审 task 准入 |
| t29-e1 | RoboTwin 的高频 review 来自项目调用路径，而非 Harness 缺少 gate | promoted | 临时脚本把判据修改、因果讨论和跳步都设为 review 点；移除后只保留根 Codex home，旧状态已备份 | 假设成立：项目采用标准 task-boundary review 即可 |
| t30-e1 | 每个 Plan Revision 一次独立准入 review 能补齐开跑前缺口，且无需新 Kernel state | promoted | 5 个 contract tests 通过：revision 去重、换 revision 重审、失败持久化、越权修改拦截、未配置兼容 | 假设成立：report adapter 独立于 task result review；下一步接 activation guard |
| t31-e1 | activation guard 能覆盖所有批准路径而不增加 lifecycle state | promoted | 25 个 plan / pause / pager 集成测试与 68 个全量测试通过；init、resume、pager、unattended 均要求当前 revision report | 假设成立：Policy 定义准入，adapter 产出 report，Harness 只守顺序 |
| t32-e1 | CLOSE Policy 足以控制 memory 增长，无需自动清理器 | promoted | RoboTwin `episodes.md` 13.6 KB → 2.1 KB（−85%），legacy 8 个文件迁出，只保留 canonical 四文件；69 个全量测试通过 | 假设成立；[案例](case_study/robotwin-memory-consolidation.md) |
| t33-e1 | Feishu 长连接可以作为独立 transport 提供自然语言双向控制，无需扩展 Kernel | promoted | pager 46 tests 与 locked verifier 通过；`lark-oapi` 1.7.3 的 Client 与 message builder 实测可构造；live app 凭据尚未提供 | 假设成立；端到端联调等待本机凭据 |
| t34-e1 | 按整行去重足以修复跨 Goal 同 id 丢行，无需引入 Goal 维度的 key | promoted | 复现测试修复前失败（新 t1 离开 active 但未进 archive），修复后通过；`(id, rev)` 不够，robotRSI 两个 plan 都有 `t1 r1` | 假设成立：只有崩溃重入会产生重复行，而它们逐字相同 |
| t35-e1 | 把领域调研挂到现有设计模板、结果写回与两个 reviewer 检查项，足以让研究型实验在设计前与否定结果后查先例，无需新机制 | active | 两个 prompt 契约测试修复前失败、修复后通过；改动 4 个既有文件，无新 state / skill / 文件 | 契约已落地；是否真的减少重走弯路，要在下一个研究型 Goal 中观察（参照 wm_forge w11 单 seed 归因） |
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

Kernel 不知道 plan 文档怎么写、实验用什么指标，也不知道任何平台的 hook JSON。它只处理：

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

Guard 是可执行条件，不写成 agent 自觉：

- plan document `Plan Revision` = task `rN` = runtime revision；
- `Plan Review` 是 `approved` 或 `unreviewed`；
- pause request 不存在；
- attempt / wall budget 尚有余额；
- verifier 通过且 workspace fingerprint 未变化。

### Policies

Policy 回答「这个状态下怎么做」，不重新定义转移：

| Policy | Owner |
|---|---|
| Goal → plan document → proposed task → review | `work-planning` |
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
下一步决策
系统 / Pipeline（确实存在才写）
Experiment Log
```

单个实验直接追加到 `Experiment Log`。只有同一 Goal 下出现多个独立实验、详细日志开始遮蔽稳定头部、
或需要并行维护时，才拆 linked `sub-exp/<id>.md`；plan document 始终保留结论与链接。
Harness 参数叫 `plan_doc`，不关心文件名是 feature、exp 还是其它名字。

task CLOSE 时，Experiment Log 的多轮记录合并为一个 task 结论；已收口内容进入 linked archive，
不继续占用活跃表。Goal CLOSE / pivot 时冻结 plan 为 as-built。原始 run、artifact 与 sub-exp 不删，
但只按 evidence 指针读取。closed task 与旧交接快照同样移出活跃 `.agent-loop/task.md` /
`progress.md`；`disproved / rejected` 因仍会阻止重复试错而保留在 memory。

CLOSE self-audit 是 `experiment-design` 的 Policy 步骤，不增加状态：worker 在 locked verifier 前回读
本 task 的完整 diff，删除过程性文案和一次性脚本，保留事实、决策分析、结论与 evidence。verifier
因此只验证最终 workspace；验证后再由 `work-planning` / reviewer 收口结论与下一步。

### Goal attention refresh

Goal Review 是 PAUSED 的一种 reason，不新增 Kernel state。默认 profile 在这些事件后要求 refresh：

- 距上次 review 已完成 3 次 runner action；
- 距上次 review 超过 60 分钟；
- 长命令结束、verify fail、evidence stale；
- adapter `COMPACT` 事件。

下一动作开始前，Policy 必须落盘四项：当前 Goal、新 evidence、下一动作为何推进 Goal、
`continue / replan / stop`。`continue` 更新 review 计数并 resume；`replan` 进入现有 revision /
review / RECONCILE；`stop` 进入 Auto-Stop。单条命令执行期间没有模型 turn，timer 只写 pause request，
反思发生在安全轮询点或命令结束后。

### Independent review boundaries

每个 Plan Revision 提交后先运行 plan reviewer，再由 human 决定 `approve / revise / stop`。
report 以 plan identity + revision 去重；reviewer 只有建议权。init、resume、pager 和无人值守
`unreviewed` 都要求有效 report。

task 验证通过后，下一步由 reviewer 决定，worker 不给自己的下一步拍板。reviewer 选中的 successor
保持 `📝 proposed`，human 或无人值守 policy 明确批准为 `🔬 doing` 后才能初始化。
两类调度都由确定性边界触发，不用 LLM 判断是否需要 review：

| 时刻 | 调用 |
|---|---|
| Plan Revision 提交、human 批准前 | reviewer 给 task 准入意见 |
| task 执行、自修、重试 | worker（宿主里的 agent） |
| task verifier 通过且配置了 reviewer | Harness 立即运行 reviewer，经 runner 执行、journal 记账 |
| reviewer 选 `ask_human` / `stop` | human |

reviewer 是项目 `.agent-loop/reviewer.json` 里的一条命令，init 时锁进 config；模型与宿主无关，原则上
强于 worker。`harness verify` 通过后在同一 orchestration 中自动调用 reviewer；决策落盘前，
runner 与下一 task 初始化都被 guard 拒绝。reviewer 只读落盘证据，改 plan / task，并写
`continue | ask_human | stop` 决策；worker 只能以事实错误异议一次，仍分歧即 `ask_human`。
调研见 [`study/multi_agent.md`](study/multi_agent.md)。

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

`HookRequest` 只使用 `TOOL_USED / COMPACT / STOP` 与 workspace、tool、status；
`HookResponse` 只使用 `ALLOW / CONTEXT / CONTINUE`。新增平台只实现两端 codec 和安装配置，
不在共享 core 中增加平台分支。自己的 driver 可以直接发送内部 request，不需要 codec。

| Adapter | 职责 |
|---|---|
| `harness/runner.py` | subprocess、process-tree kill、timeout、输出采集 |
| `harness/journal.py` | 有界 artifacts 与 `runs.jsonl` |
| `harness/plan.py` | plan metadata、task revision、pause / resume / Goal Review guard |
| `harness/plan_review.py` | plan reviewer：prompt、report 校验与 revision 去重 |
| `harness/review.py` | task 边界 reviewer：prompt、执行、决策校验与 follow-up |
| `harness/records.py` | reviewer 决策后把 closed task 移出 active backlog，并保留 archive |
| `harness/fingerprint.py` | 工作树指纹，排除 runtime 与其它 agent 的目录 |
| `harness/page.py` | human 检查点经 pager 发到手机，回复映射成 Harness 动作 |
| `harness/protocol.py` | state / event / transition；不依赖平台 |
| `adapters/protocol.py` | 平台无关的 hook request / response |
| `adapters/core.py` | 子项目发现、memory、Goal Review、completion gate 的事件处理 |
| `adapters/cursor/hooks/` | Cursor payload / output codec |
| `scripts/sync-to-cursor.ps1` | 安装 user-level adapter |

`harness/core.py` 只保留兼容 façade 与 orchestration，不再容纳平台 hook 或大段底层实现。

没有 lifecycle hooks 的壳仍可使用 rules、skills 和 Harness，属于 portable mode；只有 adapter
能接收 `STOP` 并回传 `CONTINUE` 时，才属于能强制 completion gate 的 enforced mode。

## Sources of truth

| 内容 | 唯一真相源 |
|---|---|
| Goal、当前结论、决策、active task、`rN` | plan document + `.agent-loop/task.md` |
| closed task 与旧交接点 | `.agent-loop/archive/`（只按需读取） |
| runtime phase、budget、当前 run | `.harness/state.json` |
| 原始执行证据 | `.harness/runs.jsonl` + `artifacts/`（有界） |
| 长期事实与结论 | `.agent-loop/memory/` |
| 状态与转移是否合法 | `harness/protocol.py` |

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
│   ├── core.py               # orchestration façade
│   └── run.py                # CLI
├── skills/                   # Policies
├── tools/
│   └── pager/                # 独立包：邮件往返；Harness 只经 CLI 调用
├── adapters/
│   ├── protocol.py           # platform-neutral hook boundary
│   ├── core.py               # shared hook actions
│   └── cursor/hooks/         # Cursor codec
└── study/                    # 调研与设计依据，不承担当前架构定义
```

## As-built

- `protocol.py` 持有状态与合法转移，transition tests 不依赖说明文案；
- storage / runner / journal / plan 已从 `core.py` 拆出，现有 import 继续由 core façade 提供；
- `agent-loop.mdc` 只留状态路由、硬不变量、横切 guard 与无人值守开关；
- skills index 只留 Policy owner，纠偏与 Goal Review 只在 `work-planning` 定义；
- README 只保留安装、最短使用路径、边界与文档入口。
- plan document 统一 Goal / 当前结论 / 下一步决策 / Experiment Log，详细实验只拆 linked sub-exp；
- Goal Review 由 action / elapsed / failure / stale / preCompact 事件触发，复用 PAUSED 与 revision gate。
- 每个 submitted Plan Revision 在 human 批准前运行一次独立 plan review；reviewer 只有建议权，
  init、resume、pager 与无人值守路径都不能绕过有效 report。
- 锁定 verifier 通过后由 Harness 自动运行 task-boundary reviewer；review 决策落盘前禁止执行命令
  或初始化下一 task，`continue` 只能生成 `📝 proposed` successor；批准为 `🔬 doing` 后才能初始化。
- Cursor conversation 由首次成功读取的 `.agent-loop/task.md` 绑定到一个项目；STOP 与
  preCompact 只处理该项目，避免跨 session 干扰。
- task、memory 与 configs 统一放在 `.agent-loop/`；旧 `.cursor/` runtime 只读兼容；
- task / Goal CLOSE 把 closed task、旧交接与已收口实验移出活跃工作集；reviewer 决策后 Harness
  自动归档 closed task，计划 revision 仍可从 archive 校验；
- task CLOSE 在 locked verifier 前执行 self-audit，完整回读 diff 并精炼文档、清理一次性脚本；
  这是 Policy 步骤，不增加 Kernel state；
- native hook payload 由 platform codec 归一为 `HookRequest / HookResponse`；
- public baseline 提供 Apache-2.0、CI、贡献 / 安全 / AI policy、Issue / PR 模板与安全卸载；
  maintainer runtime state 不再进入发行内容。

## Non-goals

- 不做动态 plugin loader；目录和 import 边界足够。
- 不把扁平 task 变成 DAG。
- 不让 Harness 接管未显式交给 runner 的全部 host tool call。
- 不为行数目标删判据；重构只删除重复 owner 与重复路径。

