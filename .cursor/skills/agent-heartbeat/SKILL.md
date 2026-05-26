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

当你正在执行可能超过 60 秒的操作时，**必须**遵循以下心跳协议，让用户知道你仍在正常工作。

## 职责边界

- `agent-heartbeat` 只负责长命令执行期间的状态提示。
- `long-running-agent-harness` 负责跨会话任务规划、progress log 和 handoff。
- `experiment-driven-doc` 负责实验设计和结果文档。

## 核心规则

1. **启动提示**：在执行预计耗时 > 60s 的命令前，先告诉用户预估时长：
   ```
   This may take a few minutes. I'll keep you posted.
   ```

2. **心跳输出**：如果命令运行超过 60 秒仍未返回结果，主动输出一行：
   ```
   ⏳ I'm still alive, more time needed.
   ```
   之后每隔 **60 秒**重复输出一次，直到命令完成。

3. **进度播报**：如果能从日志/输出中提取进度信息，优先播报进度而非纯心跳：
   ```
   ⏳ Still running — epoch 3/10, loss=0.42
   ⏳ Still running — compiled 1200/3000 files
   ⏳ Still running — 75% complete, ETA ~2 min
   ```

4. **完成通知**：命令结束后，立即报告结果和耗时：
   ```
   ✅ Done in 4m32s. Exit code: 0.
   ```
   或失败时：
   ```
   ❌ Failed after 2m15s. Exit code: 1. See error below.
   ```

## 触发场景

以下场景**自动启用**心跳协议（无需用户提醒）：

- `ssh` 到远端执行命令（训练、推理、编译、测试）
- `make`, `cmake`, `pip install` 等编译/安装操作
- `pytest` 跑大规模测试套件
- `docker build` / `docker run` 长时间构建
- 任何设置了 `block_until_ms: 0` 的后台命令的轮询等待
- `git clone` 大型仓库
- 模型下载（HuggingFace `from_pretrained`、`wget`、`curl` 大文件）

## 实现方式

### 方式 1：轮询后台命令时嵌入心跳

当你用 Shell 工具执行长命令并移入后台后，在轮询循环中加入心跳：

```
1. 执行命令（block_until_ms: 0 或超时后自动后台）
2. 读取 terminal 文件检查状态
3. 如果命令仍在运行：
   a. 提取最新输出中的进度信息
   b. 输出心跳/进度消息
   c. sleep 适当间隔（建议 30-60s）
   d. 回到步骤 2
4. 命令完成 → 输出完成通知
```

### 方式 2：分段执行时主动报告

如果任务被拆成多个串行步骤，在每个步骤之间报告进展：

```
Step 1/5: Cloning repository... done (12s)
Step 2/5: Installing dependencies...
⏳ Still installing — 45 packages remaining
Step 2/5: done (2m10s)
Step 3/5: Running training...
```

## 注意事项

- **不要停止思考**：心跳只是提示，输出后立即继续执行任务。
- **不要过度输出**：每 60 秒一次即可，不要每秒刷屏。
- **尊重上下文**：如果用户明确说"不需要心跳"或"安静执行"，则关闭心跳。
- **与其他 Skill 协作**：使用 `cursor-overnight-task-manager` 跑批量任务时，自动在每个 repo 的 Phase 切换时输出进度。

## 与其他 Skill 的协作

- **cursor-overnight-task-manager**：批量测试时，在 Phase 切换和单 repo 执行期间输出心跳
- **long-running-agent-harness**：按 runbook 执行长步骤时，在用户可见进度中引用当前 task id
- **local-push-remote-pull-test**：远端 pull + 测试时，报告每一步状态
- **experiment-driven-doc**：长实验运行期间，心跳中包含关键指标变化
