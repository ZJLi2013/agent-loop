---
name: tmux-remote-detach
version: 1.0.0
author: ZJLi2013
description: >-
  在远端 GPU 节点用 tmux 托管长任务，使本地 Cursor/终端可安全断开或关机。
  自动创建命名 session、日志持久化、断线恢复、批量状态检查。
  Use when running overnight tasks, long training, inference, compilation on
  remote nodes and wanting to disconnect the local machine safely.
allowed-tools: [Shell]
---

# tmux Remote Detach — 本地关机不丢任务

在远端 GPU 节点用 tmux 包裹长任务，Cursor 提交作业后本地可安全关机，
下次上线 `tmux attach` 即可恢复。

---

## 核心原则

1. **所有远端长任务必须跑在 tmux session 内**，绝不裸 `ssh … command`
2. 每个 session 用 `<repo>-<日期>` 命名，方便多任务管理
3. 命令输出同时 tee 到日志文件，即使 tmux 滚动缓冲溢出也可回查
4. 本地 SSH 只负责「创建 session + 发送命令」，之后可断开

---

## 快速参考

### 提交任务（本地 → 远端）

```bash
NODE="user@gpu-node"
SESSION="spconv-rocm-20260402"
LOGFILE="/tmp/overnight-tests/logs/${SESSION}.log"

# 创建 detached tmux session 并执行命令
ssh -A $NODE "tmux new-session -d -s $SESSION \
  'mkdir -p /tmp/overnight-tests/logs && \
   bash /tmp/overnight-tests/run.sh 2>&1 | tee $LOGFILE; \
   echo EXIT_CODE=\$? >> $LOGFILE; \
   exec bash'"
```

> `exec bash` 使任务结束后 session 不自动关闭，方便回来查看最终状态。

### 检查任务状态（本地无需 attach）

```bash
# 列出所有 tmux session
ssh $NODE "tmux ls"

# 查看日志尾部（不进入 tmux）
ssh $NODE "tail -30 $LOGFILE"

# 捕获 tmux 窗口当前屏幕内容
ssh $NODE "tmux capture-pane -t $SESSION -p | tail -20"
```

### 回来查看 / 交互

```bash
# attach 到 session（可交互）
ssh -A -t $NODE "tmux attach -t $SESSION"
```

### 任务完成后清理

```bash
ssh $NODE "tmux kill-session -t $SESSION"
```

---

## 完整工作流

### Step 1: 准备远端脚本

在本地编写执行脚本，SCP 到远端：

```bash
# 本地写脚本
cat > run_task.sh << 'SCRIPT'
#!/bin/bash
set -eu
cd /tmp/overnight-tests/spconv-rocm

export HIP_VISIBLE_DEVICES=0
export PYTORCH_ROCM_ARCH=gfx942

pip install -e . 2>&1
python -c "import spconv.pytorch as spconv; print('OK')" 2>&1
python -m pytest test/ -v 2>&1
SCRIPT

# 上传到远端
scp run_task.sh $NODE:/tmp/overnight-tests/
ssh $NODE "chmod +x /tmp/overnight-tests/run_task.sh"
```

### Step 2: 创建 tmux session 并启动

```bash
SESSION="spconv-rocm-$(date +%Y%m%d-%H%M)"
LOGFILE="/tmp/overnight-tests/logs/${SESSION}.log"

ssh -A $NODE "tmux new-session -d -s $SESSION \
  'mkdir -p /tmp/overnight-tests/logs && \
   echo \"=== START: \$(date) ===\" | tee $LOGFILE && \
   bash /tmp/overnight-tests/run_task.sh 2>&1 | tee -a $LOGFILE; \
   echo \"=== END: \$(date) EXIT_CODE=\$? ===\" | tee -a $LOGFILE; \
   exec bash'"

echo "Task submitted in tmux session: $SESSION"
echo "You can now safely close this terminal or shut down."
```

### Step 3: 本地断开 / 关机

SSH 连接断开后 tmux session 继续运行。可以：
- 关闭 Cursor
- 关机
- 等明天再查

### Step 4: 重新连接查看结果

```bash
# 方式 A: 直接看日志（快速）
ssh $NODE "cat /tmp/overnight-tests/logs/${SESSION}.log"

# 方式 B: attach 进 tmux（需要交互时）
ssh -A -t $NODE "tmux attach -t $SESSION"

# 方式 C: 拉日志到本地分析
scp $NODE:/tmp/overnight-tests/logs/${SESSION}.log ./results/
```

---

## 批量任务模式

多个 repo 在同一节点上串行/并行执行：

### 串行（推荐，共享 GPU 显存）

```bash
SESSION="overnight-batch-$(date +%Y%m%d)"
LOGFILE="/tmp/overnight-tests/logs/${SESSION}.log"

ssh -A $NODE "tmux new-session -d -s $SESSION \
  'mkdir -p /tmp/overnight-tests/logs && \
   echo \"=== BATCH START: \$(date) ===\" | tee $LOGFILE && \
   for script in /tmp/overnight-tests/tasks/*.sh; do \
     echo \"--- Running: \$script ---\" | tee -a $LOGFILE; \
     bash \$script 2>&1 | tee -a $LOGFILE; \
     echo \"--- Done: \$script EXIT=\$? ---\" | tee -a $LOGFILE; \
   done && \
   echo \"=== BATCH END: \$(date) ===\" | tee -a $LOGFILE; \
   exec bash'"
```

### 并行（多个 session，各占不同 GPU）

```bash
repos=("spconv-rocm" "RealWonder" "MotionCrafter")
gpus=(0 1 2)

for i in "${!repos[@]}"; do
  repo=${repos[$i]}
  gpu=${gpus[$i]}
  SESSION="${repo}-$(date +%Y%m%d)"

  ssh -A $NODE "tmux new-session -d -s $SESSION \
    'export HIP_VISIBLE_DEVICES=$gpu && \
     bash /tmp/overnight-tests/tasks/${repo}.sh 2>&1 \
       | tee /tmp/overnight-tests/logs/${SESSION}.log; \
     exec bash'"
done
```

### 批量状态检查

```bash
ssh $NODE "tmux ls 2>/dev/null && echo '---' && \
  for f in /tmp/overnight-tests/logs/*.log; do \
    echo \"\$(basename \$f): \$(tail -1 \$f)\"; \
  done"
```

---

## 多节点模式

跨多个 GPU 节点分发任务：

```bash
nodes=("user@gpu01" "user@gpu02" "user@gpu03")
tasks=("spconv-rocm.sh" "RealWonder.sh" "MotionCrafter.sh")

for i in "${!nodes[@]}"; do
  node=${nodes[$i]}
  task=${tasks[$i]}
  session="overnight-$(basename $task .sh)-$(date +%Y%m%d)"

  scp tasks/$task $node:/tmp/overnight-tests/
  ssh -A $node "tmux new-session -d -s $session \
    'bash /tmp/overnight-tests/$task 2>&1 \
       | tee /tmp/overnight-tests/logs/${session}.log; \
     exec bash'"
  echo "Submitted $task → $node (session: $session)"
done

echo "All tasks submitted. Safe to disconnect."
```

次日批量收集：

```bash
for node in "${nodes[@]}"; do
  echo "=== $node ==="
  ssh $node "tmux ls 2>/dev/null; echo '---'; \
    tail -5 /tmp/overnight-tests/logs/*.log 2>/dev/null"
done
```

---

## tmux 速查

| 操作 | 命令 |
|------|------|
| 列出所有 session | `tmux ls` |
| attach | `tmux attach -t <name>` |
| detach (在 tmux 内) | `Ctrl-b d` |
| kill session | `tmux kill-session -t <name>` |
| kill 所有 session | `tmux kill-server` |
| 查看滚动历史 | `Ctrl-b [` (q 退出) |
| 新窗口 | `Ctrl-b c` |
| 切换窗口 | `Ctrl-b n` / `Ctrl-b p` |

---

## PowerShell (Windows) 注意事项

从 PowerShell SSH 到远端创建 tmux session 时，引号嵌套需要特殊处理：

```powershell
# 方式 1: 写成 .sh 脚本 SCP 上去再执行（推荐）
scp run_task.sh user@gpu-node:/tmp/
ssh user@gpu-node "tmux new-session -d -s mysession 'bash /tmp/run_task.sh 2>&1 | tee /tmp/my.log; exec bash'"

# 方式 2: 用 bash -c 包裹避免引号冲突
ssh user@gpu-node "tmux new-session -d -s mysession 'bash -c ""source /tmp/run.sh""; exec bash'"
```

**最佳实践**：复杂命令一律写成 `.sh` 脚本 SCP 到远端，tmux 内只执行 `bash script.sh`。

---

## 与其他 Skill 的协作

| Skill | 协作方式 |
|-------|---------|
| **cursor-overnight-task-manager** | Phase 5 的 headless 运行改为 tmux session 内执行 |
| **agent-heartbeat** | 轮询 `tmux capture-pane` 或 `tail log` 输出心跳 |
| **gpu-cluster-resource-manager** | 节点选择后，在选中节点上创建 tmux session |
| **remote-ssh-github-auto** | `ssh -A` 保证 tmux 内可 git pull（注意: agent forwarding 仅在 SSH 连接存活时有效） |
| **experiment-driven-doc** | 从 tmux 日志中提取结果写回 experiments.md |

### Agent Forwarding 与 tmux 的限制

`ssh -A` 的 agent socket 在 SSH 断开后失效。如果 tmux session 内后续需要 `git pull`：

```bash
# 在创建 session 前，把 SSH_AUTH_SOCK 固定到已知路径
ssh -A $NODE "ln -sf \$SSH_AUTH_SOCK ~/.ssh/auth_sock_fixed"

# tmux session 内用固定路径
ssh -A $NODE "tmux new-session -d -s $SESSION \
  'export SSH_AUTH_SOCK=~/.ssh/auth_sock_fixed && bash /tmp/run.sh; exec bash'"
```

注意：断开 SSH 后此 socket 同样失效。如果任务内需要 git 操作，建议在脚本开头完成所有 `git clone/pull`。
