# agent-loop

面向 Cursor 的 agent 控制环：**默认继续，但不允许未 review 的计划、旧 revision 或未验证证据继续驱动任务。**

```text
Goal → Plan → Human Review → Run → Verify → Done
                    ↑          │
                    └─ Pause / Reconcile
```

核心分三层：

- **Stable Kernel**：状态、事件、转移和 guard；
- **Policies**：planning、task、experiment、memory、stop；
- **Adapters**：Cursor hooks、runner、verifier、git 与 execution journal。

完整边界与扩展规则见 [`design.md`](design.md)。

## 安装

```powershell
git clone https://github.com/ZJLi2013/agent-loop.git
cd agent-loop
powershell -ExecutionPolicy Bypass -File scripts/sync-to-cursor.ps1
```

脚本幂等，将 rules、skills、Harness 与 hooks 链接到 `~/.cursor/`。完成后重启 Cursor；
仓库移动、skill 增删改名后重跑。

## 新项目

初始化项目自己的 memory：

```powershell
mkdir .cursor\memory
copy $env:USERPROFILE\.cursor\skills-cursor\agent-memory\templates\*.md .cursor\memory\
```

然后直接描述 Goal。agent 会：

1. 先写一份 plan document 与最近 1–2 个 `📝 proposed` task；
2. 等待 `approve / revise / continue automatically`；
3. 每次只推进一个未验证假设；
4. 用独立 verifier 决定是否完成。

要启用 Harness，plan document 写：

```text
Plan Revision: 1
Plan Review: approved
```

`task.md` 的 `rev` 列绑定同一个 `r1`，然后初始化：

```powershell
python $env:USERPROFILE\.cursor\harness\run.py init --task t1 --plan-doc docs\plan.md `
  --timeout 300 --max-attempts 3 -- python -m pytest -q
```

运行中需要人工纠偏：

```powershell
python $env:USERPROFILE\.cursor\harness\run.py pause --require-revision --reason "Goal changed"
# 更新 plan revision / review 与 task rN
python $env:USERPROFILE\.cursor\harness\run.py resume
```

默认每 3 次 action、60 分钟、失败或 context compact 后触发 Goal Review；用
`goal-review --decision continue|replan|stop --evidence "<结论>"` 处理。

## 边界

- Harness 只硬控显式交给 runner 的命令；其它 Cursor tool call 仍由 Cursor 管。
- `task.md` 是 backlog 唯一真相源；`.harness/` 只存有界 runtime evidence。
- checkpoint / rollback 复用 git，不自动覆盖用户工作树。
- 脱离 Cursor、由外部进程掌握 agent 生命周期时，优先评估
  [BOUND](https://github.com/Danny-de-bree/bound)。

## 文档

| 文档 | 内容 |
|---|---|
| [`design.md`](design.md) | 当前架构、状态机、归属与扩展规则 |
| [`study/harness.md`](study/harness.md) | runner、journal、Verifier 与边界 |
| [`study/planning-contract.md`](study/planning-contract.md) | 渐进计划、review 与人工纠偏 |
| [`study/memory.md`](study/memory.md) | facts / episodes / lessons 的检索设计 |
| [`.cursor/skills/README.md`](.cursor/skills/README.md) | Policy 索引与唯一 owner |
