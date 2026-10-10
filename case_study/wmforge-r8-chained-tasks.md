# Case：WMForge Plan Revision 8，自动串联让 task 跳过了设计与评审

> 时间：2026-10-09 至 10-10。执行：Cursor 里的 Claude（agent-loop rules + skills）；reviewer：Codex
> `gpt-6-astra`，由项目自写的 `codex-review.sh` 手动调用；human 只在对话里给方向。远端一个 8 卡节点，
> 无人值守跑了一夜。2026-10-10 已据此补上通用控制环 guard；WMForge 的采样检查项仍由项目拥有。

## 结论

**一个没有设计文档、没过 task 级评审的数据采集 task，门一过就被脚本自动串联进 11 小时的微调；
结果新模型没过止损门，事后补文档才发现采集方案本身偏窄。** agent-loop 里本该拦住它的每一道闸门，
在这个项目上都没生效：

1. harness 是可选的，而且只认工作区根目录——这个子项目没启用，启用了 stop hook 也看不到；
2. 远端 tmux 后台作业不经过 runner，task 切换发生在 harness 之外；
3. 开跑前没有 task 级检查：设计文档是否存在、是否审过，都只靠自觉；
4. 数据采集类 task 没有假设，`experiment-design` 的模板看似不适用，只剩一个计数门；
5. plan reviewer 的 prompt 不问门的独立单位数与数据覆盖，三轮评审都放过了；
6. 无人值守条款允许自批准、不问选择题，没有禁止跨 task 自动继续，串联成了顺手的做法。

直接代价约 13 小时 × 8 卡（采集 + 微调 + 止损门），加上次日约 2.5 小时 × 8 卡的事后诊断和一整天的人工追问。

## 背景：这一轮要做什么

WMForge 用一个视频 world model（下称 WM）当 RL 环境训练机器人 policy。上一轮发现：PPO 训练后的
policy 会走到 WM 画错的地方——simulator 里失败、WM 里画成成功（「假成功」）。Plan Revision 8 的
计划是把更新后 policy 在 simulator 里的轨迹补进 WM 微调，看新 WM 能否支撑更稳的 RL：

| task | 做什么 | 门 |
|---|---|---|
| w19 | 5 个 PPO checkpoint 在 simulator 里 rollout，录帧成 WM 训练数据 | 新增失败 ≥ 150、成功 ≥ 150、录帧标签一致率 ≥ 0.97 |
| w20 | 旧数据 + w19 数据重训 WM 750 步 | val 上成功召回 ≥ 0.80，否则停 |
| w21 | 新 WM 里训 5 个 RL seed，回 simulator 比较 | 冻结的指向规则 |
| w22 | 旁支小测（双噪声复核） | 假成功翻转率 |

一个 seed 指 simulator 的一个初始状态（下称「初态」）。

## 时间线

| 时间 | 事件 | 应有的环节 |
|---|---|---|
| 10-09 07:17 | Plan Revision 8 冻结 w20 止损门与 w21 读数；codex 做过三轮 plan 级评审 | ✅ plan review |
| 07:38 | 提交 w19 采集驱动，随即开跑 | ❌ 没有 w19 设计文档、没有 w19 设计评审 |
| 09:15–09:16 | 提交 w20 驱动与 `w19_to_w20.sh`：w19 门一过就自动起 w20 | ❌ 跨 task 串联 |
| ~10:44 | w19 门 PASS（960 条、失败 167），w20 自动开训 | ❌ 没有 w19 结果写回、自审、结果评审 |
| 11:31 | 提交 `w20_to_w21.sh`：w20 门 PASS 自动起 w21（约 25–28 h） | ❌ 跨 task 串联 |
| 21:42 | w20 训完；止损门读数因缺数据崩溃，修复后 22:42 判 STOP | 串联在 STOP 时按设计停住 |
| 22:41–22:49 | human 问「w20 / w19 实验文档好像没落盘？」，两份文档此时才写 | ❌ 文档晚于实验 |
| 10-10 全天 | human 逐条追问，才查出采集方案的问题（下节） | 本该由设计评审在开跑前发现 |

w21 的设计文档反而在开跑前写好了——因为它被当成「大实验」；w19 被当成「准备数据」，就没写。

## 设计评审本该发现的问题

事后在 w19 的数据上逐项核查：

| 问题 | 数据 |
|---|---|
| **没有新增初态** | 48 个初态 × 4 遍，全是上一轮已用过的初态；上一轮还有一份 48 个初态的补采，这次没做。训练集初态 38 个，上一轮 63 个 |
| **遍数大多是重复** | 同一 policy、同一初态换一遍，85% 结果不变（1223 / 1440 对） |
| **成功没有上限** | 门只要求成功 ≥ 150，实采 793 条，占合并后训练成功池的 61% |
| **失败来自单个 policy** | 最差的一个 policy 贡献 45%（75 / 167），最好的只有 6 条 |
| **val 太小** | 按 `crc32(seed) % 8` 从 48 个初态里切，val 只有 5 个初态；32 条 val 失败有 28 条落在 2 个初态 |

w20 的止损门因此被单个初态左右：新 WM 召回 0.767（门 0.80），按初态拆开，新旧 WM 只在 2 个初态上不同；
补进的失败没有迁移到没见过的初态。这些都是**一眼能在设计阶段算出来的数**，不需要跑 11 小时。

## 机制漏洞

### 1. harness 可选，且只认工作区根目录

- `rules/agent-loop.mdc:48`：「项目存在启用中的 `.harness/state.json` 时，耗时或改变验收证据的命令经 runner」——
  条件句把强制变成可选，没启用时不提示。
- `harness/core.py:507–510`，`completion_gate`：`<root>/.harness/state.json` 不存在就 `return None`，stop hook 直接放行。
- `harness/storage.py:24–25`，`harness_dir(root)` 只取 `root / ".harness"`；`adapters/core.py` 把
  workspace roots 逐个传进去，不向下找子项目。

这个仓库是 monorepo：工作区根目录下有 `wm_forge/`、`roboJev/`、`robotRSI/` 等子项目，各自有
`.agent-loop/task.md`。WMForge 从未启用 harness；即使启用了，`wm_forge/.harness` 也不在根目录，stop hook
看不到。另两个子项目启用了 harness，同样看不到。**于是 plan → review → execute 全靠 agent 自觉**，评审
通过项目自写的 `codex-review.sh` 手动触发，想跳就能跳。

### 2. 后台作业不经过 runner

harness 只知道经 `runner` 执行的命令。WMForge 的长作业都是 `ssh` 到远端起 tmux：采集、训练、止损门、
串联脚本全在 harness 之外。`skills/agent-heartbeat` 只管「作业是否还活着」，不管作业属于哪个 task。
**task 切换被写进了远端 shell 脚本**——即使 harness 启用，它也不知道 w19 已结束、w20 已开始，更谈不上让
w19 停在 VERIFYING 等结果评审。

### 3. 开跑前没有 task 级检查

- `skills/experiment-design/SKILL.md:113`「Phase 1 — 开跑前写实验设计」是文字规定，没有任何闸门检查文档存在。
- harness 的两次评审一次在 Plan Revision 层（`harness/plan_review.py`），一次在 verifier 通过之后的 task 边界
  （`harness/review.py`）；**task 进入 RUNNING 之前没有检查点**。
- `skills/work-planning/SKILL.md:47` 规定 `task.md` 只放最近 1–2 项；r8 一次放了 4 项（w19–w22），没有校验。
  plan 表格里的一行（做法 + 门）被当成了 task 设计，而它缺 `experiment-design` 要求的假设、预期、两条出口。

项目自己在 `task.md` 写了「每个 Plan Revision 与每个 task 的设计、结果各审一次」，之前的 w12–w17、c2–c6
都有 `-design` 与 `-result` 两份评审；r8 只有三份 plan 级评审。约定写在项目里，机制不认它。

### 4. 数据采集类 task 掉进空档

`experiment-design` 的模板围绕「假设 → 判据」。w19 没有假设，只是「采数据」，模板看似不适用；它的门
只检查条数与标签一致率。机制里没有针对**数据产出类 task** 的检查项：新增多少初态（独立单位）、
每个初态重复几遍、按来源的配额、成功上限、留出集有多少个独立单位。

### 5. plan reviewer 不问样本单位与覆盖

`harness/plan_review.py:41–48` 的五条检查：验收判据能否支持结论、两个出口是否不同、昂贵动作前是否缺
廉价前置、研究型 task 是否缺领域先例、只报会改变决定的问题。**没有一条问「门按独立单位有多少个」或
「数据覆盖相对上一轮怎样」。** 项目的 codex 评审请求同样没问。三轮评审的注意力都在 w21 的 seed 配对与区间上；
w19 的设计评审原文甚至写了「只采这 48 个初态合适……重复 rollout 不算新增独立初态」——它看到了重复，
却只当成一条记账说明。

### 6. 无人值守条款鼓励自动继续

`rules/agent-loop.mdc:51–57`：Human Review Gate 自批准、不问选择题、blocked 跳过做下一条。条款没有说
「跨 task 必须停在结果评审」，也没有说「自批准不等于跳过 reviewer」（这一条只写在
`skills/work-planning/SKILL.md:52–53`）。节点慢（训练 52 s / 步）、不想让 GPU 空转，串联脚本就是最自然的选择。

## 修复

| 漏洞 | 通用修复 | 状态 |
|---|---|---|
| 子项目未启用 Harness | 子项目需作为 workspace root 打开；stop hook 只检查该 root，避免跨 session 干扰 | 已实施 |
| 后台作业越过 task 边界 | 启动命令经 runner 留下 task id / run id；heartbeat 与 remote-exec 明确 detach 只跨进程，同一 task 未 verify / review 前不能初始化 successor | 已实施；外部脚本内容不可自动审计 |
| 开跑前没有 task 级设计门 | reviewer prompt 要求 task 链接设计；successor 必须由上一 task reviewer 写成 `📝 proposed`，批准为 `🔬 doing` 后 Harness 才允许初始化 | 已实施 |
| 数据采集设计缺口 | 独立单位、重复、配额、类别上限与留出集是 WMForge 的领域检查项，不写进通用 `experiment-design` | 项目侧修复 |
| reviewer 没问数据覆盖 | WMForge reviewer prompt 应按该项目的数据生成过程检查独立单位与覆盖；agent-loop 只要求可评审设计和能支撑结论的判据 | 项目侧修复 |
| 无人值守自动继续 | 自批准不再跳过 reviewer；明确禁止跨 task 自动继续 | 已实施 |

## 项目侧仍需要

- 每个 task（包括采数据、训模型）开跑前写设计文档，并单独送 reviewer；plan 表格的一行不算。
- 设计里写清门的独立单位：多少个初态 / 训练 run / 场景，而不是多少条片段。
- 远端串联只用于同一个 task 内部；task 之间停下来写结果、过结果评审。
- 评审请求点名两件事：每个门的独立单位数，数据覆盖相对上一轮的增减。

## 证据

均在 `robot_rl_from_zero_to_expert` 仓库：

- 采集方案的问题：`wm_forge/exps/robotwin_bwm/onpolicy_refine/w19-onpolicy-collect.md`「采集方案的问题」
- 止损门结果与初态拆分：`wm_forge/exps/robotwin_bwm/onpolicy_refine/w20-wm-finetune.md`「初态多样性」
- 评审记录：`wm_forge/.agent-loop/reviews/20261009-r8-plan.codex.md`（「只采 hires48 合适」）、
  `20261009-w20-result.codex.md`（事后的结果评审）；r8 没有 `w19-design` / `w20-design` 文件
- 串联脚本：`wm_forge/script/w19_to_w20.sh`、`wm_forge/script/w20_to_w21.sh`
- 初态集合与重叠：`robotwin/adjust-bottle-seeds.md`
