# 最小 Harness

## Goal

把 agent-loop 从模型自觉遵守的建议，变成由模型之外的 runner、verifier 和 completion gate
共同推进的实际控制流。

## 结论

最小 Harness 已落地：显式 runner 命令受 hard timeout、attempt / wall budget 和有界 journal 控制；
锁定 verifier 通过且工作树未变化时，stop hook 才允许 Cursor 结束。它不拦截所有 Cursor tool call，
任务状态仍以 `.cursor/task.md` 为唯一真相源。

## Pipeline

```text
agent 选择动作
  │
  ├─ run exec ─► hard timeout ─► bounded stdout/stderr ─► runs.jsonl
  │
  └─ run verify ─► 锁定的 verifier ─► fingerprint
                                      │
Cursor stop hook ─────────────────────┤
  ├─ verified + fingerprint 未变 ─► 允许结束
  ├─ 还有预算 ─► followup_message ─► DIAGNOSE / REPAIR
  └─ 预算耗尽 ─► 允许 Auto-Stop
```

源码安装在 `~/.cursor/harness/`；每个工作项目的运行状态放在 `.harness/`：

```text
.harness/
├── config.json       # verifier 与硬预算；初始化后锁定
├── state.json        # 当前 phase / attempt / budget，不复制 task 内容
├── runs.jsonl        # 有界执行摘要
└── artifacts/        # 有界 stdout/stderr
```

## Contract

- `task.md` 管「做哪件事」；Harness 只管「哪条命令跑过、证据是否有效、还能不能继续」。
- `exit 0` 只表示命令成功；只有 verifier 通过且工作树 fingerprint 未变化，task 才可完成。
- retry 由 agent 诊断后产生不同动作；Harness 只计数并拒绝超预算，不原样自动重跑。
- stdout/stderr 先脱敏再持久化，单流和 artifact 数量都有硬上限；memory 只引用 run id，不复制日志。
- checkpoint 使用 git，不在 `.harness/checkpoints/` 复制工作树。

## Tests

`python -m unittest discover -s tests -v` 的 12 个测试覆盖：

- pass / non-zero exit / timeout / process-tree cleanup；
- attempt 与总 wall budget；
- stdout/stderr 脱敏、截断、artifact 与 journal 上限；
- config 锁定、输出契约拒绝 exit-0 假通过；
- 未验证续跑、验证后改码失效、预算耗尽只要求一次 Auto-Stop Report。

[`harness/core.py`](../harness/core.py) 是 runner 与状态机；[`harness-stop.py`](../.cursor/hooks/harness-stop.py)
把状态接到 Cursor `stop.followup_message`；[`sync-to-cursor.ps1`](../scripts/sync-to-cursor.ps1) 将二者
安装到 user 级。完整强制边界仍需外部 driver 拥有 agent 生命周期；离开 Cursor 时优先评估 BOUND。

