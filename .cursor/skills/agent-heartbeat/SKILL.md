---
name: agent-heartbeat
description: >-
  AI 助手在执行耗时任务（远端 GPU 训练、推理、编译、大规模测试等）时，自动输出
  心跳消息防止用户误判为卡死。Use when running long SSH commands, remote GPU
  tasks, training, inference, compilation, overnight tests, or any command
  expected to take more than 60 seconds. This skill owns user-visible runtime
  status updates, not task planning or experiment documentation.
---

# Agent Heartbeat — 长任务活跃提示

执行可能超过 60 秒的操作时**必须**心跳，让用户知道你没卡死。

**边界**：本 skill 只管命令执行期间的状态提示；跨会话规划与 handoff 归
`long-running-agent-harness`，实验设计与结果归 `experiment-driven-doc`。

## 协议

| 时机 | 输出 |
|---|---|
| 开跑前（预计 > 60s） | `This may take a few minutes. I'll keep you posted.` |
| 每 60 秒 | `⏳ I'm still alive, more time needed.` |
| 能从日志提取进度时（优先） | `⏳ Still running — epoch 3/10, loss=0.42` |
| 结束 | `✅ Done in 4m32s. Exit code: 0.` / `❌ Failed after 2m15s. Exit code: 1.` |

**能播报进度就不要只播心跳。** 纯心跳只说明进程活着，进度才说明它在推进。

## 自动启用的场景

`ssh` 远端执行（训练 / 推理 / 编译 / 测试）、`make`/`cmake`/`pip install`、大规模 `pytest`、
`docker build`/`run`、大仓库 `git clone`、模型下载，以及任何后台命令（`block_until_ms: 0`）的轮询等待。

轮询循环里嵌心跳：读 terminal 文件 → 仍在跑就提取进度并输出一行 → sleep 30–60s → 回到读取。
任务被拆成串行步骤时改为步骤间报告（`Step 2/5: Installing dependencies... done (2m10s)`）。

## 注意

- **心跳不打断工作**：输出后立即继续，不要停下来等。
- **不要刷屏**：60 秒一次，不是每秒一次。
- 用户说「安静执行」就关掉。

## 与其他 Skill 的协作

- **cursor-overnight-task-manager**：Phase 切换与单 repo 执行期间播报
- **tmux-remote-detach**：轮询 `capture-pane` / `tail log` 作为进度来源
- **long-running-agent-harness**：心跳里带上当前 task id
- **experiment-driven-doc**：长实验的心跳里带关键指标变化
