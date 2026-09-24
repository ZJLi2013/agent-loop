# agent-loop

[![tests](https://github.com/ZJLi2013/agent-loop/actions/workflows/test.yml/badge.svg)](https://github.com/ZJLi2013/agent-loop/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

平台无关的 agent 控制环：**默认继续，但不允许未 review 的计划、旧 revision 或未验证证据继续驱动任务。**

```text
Goal → Plan → Human Review → Run → Verify → Reviewer → next task / Done
                    ↑          │                 │
                    └─ Pause / Reconcile ◄───────┘ ask_human
```

worker 执行 task；task 验证通过后，下一步由 reviewer（可配置的另一个模型）决定，调度由 Harness 状态机完成。

核心分三层：

- **Stable Kernel**：状态、事件、转移和 guard；
- **Policies**：planning、task、experiment、memory、stop；
- **Adapters**：platform codecs、runner、verifier、git 与 execution journal。

完整边界与扩展规则见 [`design.md`](design.md)。

## 安装

```powershell
git clone https://github.com/ZJLi2013/agent-loop.git
cd agent-loop
python -m pip install -e .
```

核心 CLI 与项目 runtime 不依赖宿主。当前仓库另提供 Cursor enforced adapter：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync-to-cursor.ps1
```

脚本幂等，将 rules、skills、Harness 与 Cursor codec 链接到 `~/.cursor/`。完成后重启 Cursor；
仓库移动、skill 增删改名后重跑。

> Cursor adapter 会创建 user-level junction，并让本地 Python hook 在所有 workspace 运行。
> 请先审阅并固定可信 commit；完整边界见 [`SECURITY.md`](SECURITY.md)。

卸载只移除 agent-loop 自己的 links 与 hook entries，不删除备份：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/uninstall-from-cursor.ps1
```

## 支持范围

| Component | Status |
|---|---|
| Platform-neutral Harness CLI | Python 3.11 / 3.13; Windows and Ubuntu CI tested |
| Cursor enforced adapter | Windows + PowerShell 5.1 installer supported |
| macOS/Linux installer | Roadmap；当前需手动 symlink |

## 新项目

初始化项目自己的 memory：

```powershell
mkdir .agent-loop\memory
$agentLoopRepo = "C:\path\to\agent-loop"
copy "$agentLoopRepo\skills\agent-memory\templates\*.md" .agent-loop\memory\
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
agent-loop-harness init --task t1 --plan-doc docs\plan.md `
  --timeout 300 --max-attempts 3 -- python -m pytest -q
```

运行中需要人工纠偏：

```powershell
agent-loop-harness pause --require-revision --reason "Goal changed"
# 更新 plan revision / review 与 task rN
agent-loop-harness resume
```

默认每 3 次 action、60 分钟、失败或 context compact 后触发 Goal Review；用
`goal-review --decision continue|replan|stop --evidence "<结论>"` 处理。

task 边界的下一步可以交给另一个模型：init 前写 `.agent-loop/reviewer.json`，任意能在项目目录
读写文件的 CLI 都行，原则上 reviewer 强于 worker。例：Cursor 里的 agent 当 worker，WSL 里的 Codex 当 reviewer：

```json
{
  "argv": ["wsl.exe", "--", "bash", "-lc",
           "codex exec -s workspace-write 'Read .harness/review/prompt.md and follow it exactly.'"],
  "timeout_seconds": 1800
}
```

verify 通过后 stop hook 会要求 `agent-loop-harness review`；reviewer 改写 `task.md` 并写
`continue | ask_human | stop`，worker 只能以事实错误异议一次。

最小可运行样例见 [`examples/minimal-project/`](examples/minimal-project/)。

## 边界

- Harness 只硬控显式交给 runner 的命令；其它 host tool call 仍由宿主管理。
- `task.md` 是 backlog 唯一真相源；`.harness/` 只存有界 runtime evidence。
- `.agent-loop/task.md` 与 `.agent-loop/memory/` 是项目本地 runtime；旧 `.cursor/` 路径只读兼容。
- checkpoint / rollback 复用 git，不自动覆盖用户工作树。
- 没有 lifecycle hooks 的宿主属于 portable mode，不能强制 completion gate；外部进程掌握 agent
  生命周期时可评估 [BOUND](https://github.com/Danny-de-bree/bound)。

## 文档

| 文档 | 内容 |
|---|---|
| [`design.md`](design.md) | 当前架构、状态机、归属与扩展规则 |
| [`study/harness.md`](study/harness.md) | runner、journal、Verifier 与边界 |
| [`study/planning-contract.md`](study/planning-contract.md) | 渐进计划、review 与人工纠偏 |
| [`study/memory.md`](study/memory.md) | facts / episodes / lessons 的检索设计 |
| [`study/multi_agent.md`](study/multi_agent.md) | 现有 multi-agent loop 对比与 worker / reviewer 分工 |
| [`case_study/robojev-nox.md`](case_study/robojev-nox.md) | 一天 11 个 task 边界的跨模型纠偏记录 |
| [`skills/README.md`](skills/README.md) | Policy 索引与唯一 owner |
| [`CONTRIBUTING.md`](CONTRIBUTING.md) | 贡献流程、新 feature 准入与测试 |
| [`AI_POLICY.md`](AI_POLICY.md) | AI-assisted contribution 披露 |
| [`SECURITY.md`](SECURITY.md) | 安全边界与私密报告渠道 |
| [`CHANGELOG.md`](CHANGELOG.md) | 用户可感知变化 |
| [`ROADMAP.md`](ROADMAP.md) | Now / Next / Later |

Apache-2.0 licensed. Security issues must use private vulnerability reporting, not public Issues.
