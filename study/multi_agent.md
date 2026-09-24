# Multi-agent loop 调研

> 2026-09 读的是各项目的公开文档与 README，只看角色划分与调度方式；标「未实测」的没有跑过。

## 结论

**agent-loop 只要两个 agent 角色，调度留在代码里。** worker 执行 task，reviewer 在 task 边界决定下一步；
「什么时候叫谁」是一张固定的状态表，由 Harness 的状态机执行，不另设 LLM 调度 agent。

依据来自 [RoboJEV × Nox-4B case](../case_study/robojev-nox.md)：11 个 task 边界里，决策几乎每次都被
改写，执行一次都没有。需要判断的只有边界这一个时刻，所以 LLM 调度器只会多出一个会漂移的判断点。

## 现有实现

| 实现 | 角色与调度 | 可借鉴 | 不适用的地方 |
|---|---|---|---|
| [Magentic-One](https://microsoft.github.io/autogen/stable/user-guide/agentchat-user-guide/magentic-one.html)（AutoGen / Agent Framework） | LLM Orchestrator 管两层循环：外层 task ledger（事实、猜测、计划），内层 progress ledger 决定下一个执行者；卡住计数超阈值回外层重规划 | 外层 ledger ≈ plan document；卡住计数 ≈ `when-to-stop`；官方建议 Orchestrator 用强推理模型，也试过外层 o1、其余 GPT-4o | 面向开放式网页 / 文件任务；每步都由 LLM 选执行者，没有实验证据、预算、Goal 审批 |
| [Aider architect mode](https://aider.chat/docs/usage/modes.html) | 强推理模型出方案，editor 模型改文件 | 「强模型判断、另一个模型执行」的分工 | 粒度是单次请求，不跨 task |
| [multi-agent-todo](https://github.com/airborne12/multi-agent-todo)（未实测） | Planner → Coder → 多个 Reviewer 投票，每个角色可配模型，被拒退回 Coder；每个 task 一个 worktree | 角色模型可配置 | reviewer 审代码 diff，不决定下一个实验 |
| [opencode-orchestrator](https://cdn.jsdelivr.net/npm/opencode-orchestrator@1.5.0/README.md)（未实测） | Commander / Planner / Worker / Reviewer，各自可配模型，mission ledger | 同上 | 同上，Commander 仍是 LLM |
| [LangGraph](https://docs.langchain.com/oss/python/langgraph/graph-api) | 图 + 条件边 + 递归上限 | 调度写成代码里的条件边 | 只是构件，要自己搭 |

共同点：reviewer 审「这次改动对不对」。agent-loop 要的是审「证据说明了什么、下一步做什么」，
并且在 Goal / scope 变化时交回 human。

## agent-loop 的做法

| 时刻 | 调用 |
|---|---|
| task 执行、自修、重试 | worker：宿主里的 agent |
| task `VERIFIED` 且配置了 reviewer | reviewer：`harness review` |
| reviewer 选 `ask_human` / `stop` | human |
| 预算用尽、中止清单 | 停 |

- **模型不写死。** reviewer 是 `.agent-loop/reviewer.json` 里的一条命令，原则上强于 worker。
  Cursor 里用不到的模型（如 Codex 里的 gpt-6）走 `wsl.exe -- bash -lc "codex exec ..."`。
- **reviewer 只读落盘证据。** 不给 worker 的对话；新上下文本身是收益的一部分。
- **worker 只能以事实错误异议一次**（路径、数字、已做过、跑不了、超预算），仍分歧即 `ask_human`。
- **挂在已有的 completion gate 上。** Cursor stop hook 在 `VERIFIED` 后返回 CONTINUE，要求 worker
  跑 `review`；reviewer 经 runner 执行，受超时约束并记入 journal，不在 hook 里同步等待。
