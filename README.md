# agent-loop

[English](en.md) · [快速开始](docs/quickstart.md) · [使用指南](docs/usage.md) · [相关项目](docs/related-projects.md)

[![tests](https://github.com/ZJLi2013/agent-loop/actions/workflows/test.yml/badge.svg)](https://github.com/ZJLi2013/agent-loop/actions/workflows/test.yml)
[![License](https://img.shields.io/badge/license-Apache--2.0-blue.svg)](LICENSE)

**让 coding agent 持续推进研究与工程项目：逐步规划、执行、验证，再根据证据决定下一步。**

agent-loop 为现有 agent 提供项目级控制环。适合多轮实验、需要验证的工程改造，以及需要跨上下文
接续的长任务。你定义 Goal 和项目判据，worker 执行，独立 verifier 验证；可选 reviewer
核对证据、提出下一步，方向变化时交回 human。

```text
Goal → Plan → Human Review → Execute → Verify → Review → next task / human / stop
                                  ↑                        │
                                  └──── approved next task ┘
```

当前版本定位为 **0.1.0 early release**；发布状态以 [GitHub Releases](https://github.com/ZJLi2013/agent-loop/releases)
为准。配置与状态格式仍可能演进，变更记录在 [CHANGELOG](CHANGELOG.md)。

## 它负责什么

- **渐进规划**：每次推进一个待验证假设，plan revision 防止旧任务继续驱动工作。
- **执行与完成判据**：显式 runner 控制超时、预算和日志；锁定 verifier 验证项目结果，工作树变化会使证据失效。
- **边界评审**：可选 reviewer 在计划提交与任务验证后运行；human 保留目标和计划批准权。
- **跨轮接续**：项目 memory、当前交接和记录归档，让后续上下文找得到已有结论。
- **长任务观察与人工检查点**：提供心跳 policy；可选 pager 将检查点送到手机。

实验指标和测试由工作项目定义。agent-loop 不预设某个研究领域，也不要求固定模型搭配。

## 先跑通一次

需要 Python 3.11+、pip 和 Git。以下从仓库根目录开始，PowerShell 与 Bash 均可执行；Linux 上
若只有 `python3`，将 `python` 替换为 `python3`。可先激活自己的虚拟环境。

```sh
git clone https://github.com/ZJLi2013/agent-loop.git
cd agent-loop
python -m pip install .
python examples/minimal-project/prepare.py ../agent-loop-demo
cd ../agent-loop-demo
agent-loop-harness init --task t1 --plan-doc plan.md -- python -B -m unittest -v
agent-loop-harness verify
```

第一次验证**预期失败，退出码为 1**：示例把平均值错误地做了整数除法。完整的
[快速开始](docs/quickstart.md) 会带你检查证据、完成 Goal Review、修复代码并重新验证。
示例无需 API key、模型或 Cursor，也不会安装全局 hooks。

这段命令跟随默认分支；已有 release 时，安装前可 `git checkout v0.1.0` 固定对应版本。
完整使用通过仓库 checkout 分发，Python 包只安装 CLI 与 adapter 代码。

## 接到日常工作

CLI 跑通后，在 Windows + Cursor 下安装 enforced adapter（从仓库根目录执行）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync-to-cursor.ps1
```

安装器会创建 user-level junction 和 hooks，并将已有同名普通目录备份。保持仓库路径可用，
重启 Cursor，并确保它能找到 `python`。hooks 会在宿主覆盖的 workspace 中执行本地代码；安装前
阅读 [安全边界](SECURITY.md)。卸载使用 `scripts/uninstall-from-cursor.ps1`，备份需自行恢复。

[使用指南](docs/usage.md) 包含新项目初始化、reviewer、暂停纠偏、memory、pager 和升级步骤。

## 支持范围与边界

| 部分 | v0.1 支持范围 |
|---|---|
| Harness CLI | Python 3.11+；CI 配置覆盖 Windows / Ubuntu，Python 3.11 / 3.13 |
| Cursor enforced adapter | Windows + PowerShell 5.1 安装器；依赖宿主 lifecycle hooks |
| 其他宿主 | 可使用 portable CLI / policies；不承诺强制 completion gate |
| macOS/Linux 宿主安装器 | 尚未提供；CLI 与宿主全局安装是两个层次 |
| reviewer / pager | 可选命令与独立组件，需要额外配置 |

Harness 只硬控显式交给 runner 的命令，其余工具调用由宿主管理。pager 不能唤醒已退出的 agent；
无人值守等待需要会话、电脑和网络在线。checkpoint / rollback 复用 git，不自动覆盖工作树。

## 与其他项目的关系

[Ralph](https://github.com/snarktank/ralph) 围绕 PRD 条目循环执行，
[autoresearch](https://github.com/karpathy/autoresearch) 围绕固定训练指标试验；agent-loop 聚焦
跨研究与工程项目的计划、项目验证和边界评审。完整对照还包括 Aider、mini-swe-agent、
OpenHands 和 LangGraph，见 [相关项目与选择依据](docs/related-projects.md)。这是一份用途对照，未做性能排名。

## 文档与贡献

| 想做什么 | 入口 |
|---|---|
| 安装并体验失败到通过 | [Quickstart](docs/quickstart.md) |
| 在工作项目中使用 | [Usage](docs/usage.md) |
| 理解架构与扩展边界 | [design.md](design.md) · [Policies](skills/README.md) |
| 阅读调研与实际案例 | [Study 地图](docs/study/README.md) · [案例索引](case_study/README.md) |
| 查看版本与发布流程 | [Changelog](CHANGELOG.md) · [v0.1.0 notes](docs/releases/v0.1.0.md) · [Release guide](docs/releasing.md) |
| 报告问题或贡献 | [Issues](https://github.com/ZJLi2013/agent-loop/issues) · [Contributing](CONTRIBUTING.md) · [Roadmap](ROADMAP.md) |

欢迎提供安装失败、宿主版本兼容、错误完成判断、重复劳动和 review 开销的最小复现。
AI 辅助贡献需遵循 [AI_POLICY.md](AI_POLICY.md)。漏洞请走 [私密报告渠道](SECURITY.md)，不要发公开 Issue。

Apache-2.0，见 [LICENSE](LICENSE)。
