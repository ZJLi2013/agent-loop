# 最小 Harness

## Goal

把 agent-loop 从模型自觉遵守的建议，变成由模型之外的 runner、verifier 和 completion gate
共同推进的实际控制流。

## 结论

最小 Harness 已落地：显式 runner 命令受 hard timeout、attempt / wall budget 和有界 journal 控制；
锁定 verifier 通过且工作树未变化时，enforced adapter 才允许宿主结束。它不拦截所有 host tool call，
任务状态仍以 `.agent-loop/task.md` 为唯一真相源。运行中 pause 与 Plan Revision gate 已落地。

## Pipeline

```text
agent 选择动作
  │
  ├─ run exec ─► hard timeout ─► bounded stdout/stderr ─► runs.jsonl
  │
  └─ run verify ─► 锁定的 verifier ─► fingerprint
                                      │
human pause ─► 中断 runner ─► plan revision + review + task rN ─► resume
                                      │
adapter STOP ─────────────────────────┤
  ├─ verified + fingerprint 未变 ─► 允许结束
  ├─ 还有预算 ─► followup_message ─► DIAGNOSE / REPAIR
  └─ 预算耗尽 ─► 允许 Auto-Stop
```

CLI 通过 `agent-loop-harness` 调用；每个工作项目的运行状态放在 `.harness/`：

```text
.harness/
├── config.json       # verifier 与硬预算；初始化后锁定
├── state.json        # 当前 phase / attempt / budget，不复制 task 内容
├── pause.json        # 无锁 pause request；运行中的 runner 轮询它
├── runs.jsonl        # 有界执行摘要
└── artifacts/        # 有界 stdout/stderr
```

## Contract

- `task.md` 管「做哪件事」；Harness 只管「哪条命令跑过、证据是否有效、还能不能继续」。
- `exit 0` 只表示命令成功；只有 verifier 通过且工作树 fingerprint 未变化，task 才可完成。
- retry 由 agent 诊断后产生不同动作；Harness 只计数并拒绝超预算，不原样自动重跑。
- task 锁定 plan document 的 `Plan Revision`；review、task `rN` 与 Harness state 不一致时拒绝运行。
- pause request 不等 state lock，可中断长命令；human correction 要求 revision 递增后才能 resume。
- action count、elapsed time、失败、evidence stale 与 preCompact 共用 pause gate 触发 Goal Review。
- stdout/stderr 先脱敏再持久化，单流和 artifact 数量都有硬上限；memory 只引用 run id，不复制日志。
- checkpoint 使用 git，不在 `.harness/checkpoints/` 复制工作树。

## Tests

`python -m unittest discover -s tests -v` 覆盖：

- pass / non-zero exit / timeout / process-tree cleanup；
- attempt 与总 wall budget；
- stdout/stderr 脱敏、截断、artifact 与 journal 上限；
- config 锁定、输出契约拒绝 exit-0 假通过；
- 未验证续跑、验证后改码失效、预算耗尽只要求一次 Auto-Stop Report。
- proposed plan 自动暂停、运行中 pause、revision / review / task `rN` 一致后 resume。
- Goal Review 的 action / time / failure 触发，以及 continue / replan / stop 与 preCompact adapter。

[`protocol.py`](../harness/protocol.py) 定义状态机；storage / runner / journal / plan 各持一个职责，
[`core.py`](../harness/core.py) 只做 orchestration 与兼容 façade。[`adapters/core.py`](../adapters/core.py)
把共享动作接到内部 hook protocol，Cursor codec 再翻译成 `stop.followup_message`。完整强制边界仍需
宿主 hook 或外部 driver 拥有 agent 生命周期。

