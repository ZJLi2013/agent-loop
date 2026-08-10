---
name: tmux-remote-detach
version: 1.0.0
author: ZJLi2013
description: >-
  在远端 GPU 节点用 tmux 托管长任务，使本地 Cursor/终端可安全断开或关机。
  自动创建命名 session、日志持久化、断线恢复、批量状态检查。
  Use when running overnight tasks, long training, inference, compilation on
  remote nodes and wanting to disconnect the local machine safely. This skill
  owns remote process persistence; use long-running-agent-harness for the
  larger task plan and handoff.
disable-model-invocation: true
allowed-tools: [Shell]
---

# tmux Remote Detach — 本地关机不丢任务

远端长任务包在 tmux 里，提交后本地可以关 Cursor、关机，下次 `tmux attach` 恢复。

**边界**：本 skill 只管「进程活下来 + 日志可回查」；为什么跑、属于哪个 task、怎么验证、
下一位 agent 怎么接手，归 `long-running-agent-harness`（把 session 名、日志路径、恢复命令
写进 `progress.md`）。

## 四条原则

1. **远端长任务必须跑在 tmux 内**，绝不裸 `ssh … command`
2. session 名统一 `<repo>-<日期>`，多任务好辨认
3. 输出 `tee` 到日志文件——tmux 滚动缓冲会溢出，日志不会
4. 本地 SSH 只负责「建 session + 发命令」，之后随时可断

## 提交与查看

```bash
NODE="user@gpu-node"; SESSION="spconv-rocm-$(date +%Y%m%d-%H%M)"
LOG="/tmp/overnight-tests/logs/${SESSION}.log"

ssh -A $NODE "tmux new-session -d -s $SESSION \
  'mkdir -p /tmp/overnight-tests/logs && \
   echo \"=== START \$(date) ===\" | tee $LOG && \
   bash /tmp/overnight-tests/run_task.sh 2>&1 | tee -a $LOG; \
   echo \"=== END \$(date) EXIT=\$? ===\" | tee -a $LOG; \
   exec bash'"
```

`exec bash` 让任务结束后 session 不自动消失，回来还能看最终状态。

| 目的 | 命令 |
|---|---|
| 列 session | `ssh $NODE "tmux ls"` |
| 看日志尾（不 attach） | `ssh $NODE "tail -30 $LOG"` |
| 看当前屏幕 | `ssh $NODE "tmux capture-pane -t $SESSION -p \| tail -20"` |
| 进去交互 | `ssh -A -t $NODE "tmux attach -t $SESSION"` |
| 收工 | `ssh $NODE "tmux kill-session -t $SESSION"` |
| 批量状态 | `ssh $NODE "tmux ls; for f in .../logs/*.log; do echo \"\$f: \$(tail -1 \$f)\"; done"` |

tmux 内快捷键：`Ctrl-b d` detach、`Ctrl-b [` 翻历史（`q` 退出）、`Ctrl-b c/n/p` 新建与切窗口。

## 批量与多节点

同一个 `new-session` 模式套循环即可，三种排布：

- **单节点串行**（推荐，共享显存）：session 内 `for script in tasks/*.sh; do bash $script; done`
- **单节点并行**：每个 repo 一个 session，各自 `export HIP_VISIBLE_DEVICES=<i>`
- **跨节点**：先 `scp` 任务脚本，再对每个节点建一个 session

```bash
for i in "${!repos[@]}"; do
  s="${repos[$i]}-$(date +%Y%m%d)"
  ssh -A $NODE "tmux new-session -d -s $s \
    'export HIP_VISIBLE_DEVICES=${gpus[$i]} && \
     bash /tmp/overnight-tests/tasks/${repos[$i]}.sh 2>&1 | tee /tmp/overnight-tests/logs/$s.log; \
     exec bash'"
done
```

次日收集：对每个节点 `tmux ls` + `tail -5 logs/*.log`。

## 两个坑

**PowerShell 引号嵌套**：复杂命令一律写成 `.sh` 脚本 `scp` 上去，tmux 里只执行 `bash script.sh`。
在 PowerShell 里拼多层引号几乎必翻车。

**`ssh -A` 的 agent socket 在 SSH 断开后失效**，tmux 里后续的 `git pull` 会挂。
把所有 `git clone/pull` 放在脚本开头、SSH 还连着的时候做完。硬要延后就先固定 socket
（`ln -sf $SSH_AUTH_SOCK ~/.ssh/auth_sock_fixed`，session 内 export 它）——但断开后同样失效。

## 与其他 Skill 的协作

| Skill | 协作方式 |
|---|---|
| **cursor-overnight-task-manager** | Phase 5 的 headless 运行放进 tmux |
| **gpu-cluster-resource-manager** | 选定节点后在其上建 session |
| **agent-heartbeat** | 轮询 `capture-pane` 或 `tail log` 输出心跳 |
| **long-running-agent-harness** | 记录 session / log path / 恢复命令 / handoff |
| **experiment-driven-doc** | 从日志提取结果写回实验文档 |
