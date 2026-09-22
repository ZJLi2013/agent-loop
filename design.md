# agent-loop Design

Plan Revision: 4
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
| `harness/protocol.py` | state / event / transition；不依赖平台 |
| `adapters/protocol.py` | 平台无关的 hook request / response |
| `adapters/core.py` | memory、Goal Review、completion gate 的事件处理 |
| `adapters/cursor/hooks/` | Cursor payload / output codec |
| `scripts/sync-to-cursor.ps1` | 安装 user-level adapter |

`harness/core.py` 只保留兼容 façade 与 orchestration，不再容纳平台 hook 或大段底层实现。

没有 lifecycle hooks 的壳仍可使用 rules、skills 和 Harness，属于 portable mode；只有 adapter
能接收 `STOP` 并回传 `CONTINUE` 时，才属于能强制 completion gate 的 enforced mode。

## Sources of truth

| 内容 | 唯一真相源 |
|---|---|
| Goal、当前结论、决策、task、`rN` | plan document + `.agent-loop/task.md` |
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
│   ├── core.py               # orchestration façade
│   └── run.py                # CLI
├── skills/                   # Policies
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
- task、memory 与 configs 统一放在 `.agent-loop/`；旧 `.cursor/` runtime 只读兼容；
- native hook payload 由 platform codec 归一为 `HookRequest / HookResponse`；
- public baseline 提供 Apache-2.0、CI、贡献 / 安全 / AI policy、Issue / PR 模板与安全卸载；
  maintainer runtime state 不再进入发行内容。

## Non-goals

- 不做动态 plugin loader；目录和 import 边界足够。
- 不把扁平 task 变成 DAG。
- 不让 Harness 接管未显式交给 runner 的全部 host tool call。
- 不为行数目标删判据；重构只删除重复 owner 与重复路径。

