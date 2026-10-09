---
name: agent-heartbeat
description: >-
  观察 detach 的长任务是否还活着：到机器的连接还在，远端日志仍有预期输出。
  训练、评测、编译或其他预计超过 30 分钟的后台任务用它。
  心跳间隔由预计时长决定，约 1 小时每 10 分钟，10 小时及以上每 30 分钟。
---

# Agent Heartbeat

detach 的长任务要能看出两件事：到那台机器的连接还在，以及远端脚本仍在写出预期内容。进程还在、但有效日志不再增长，算挂住。

**边界**：跨会话交接归 `task-state`，实验结论归 `experiment-design`，上机、detach、短 SSH 归 `remote-exec`。

预计短于 30 分钟：不挂观察。开跑前一句，结束时报耗时和退出码。

## 间隔

间隔分钟数 = clamp(预计秒数 / 360, 10, 30)。不要手改这个数。

| 预计 | 间隔 | 挂死线（连续两拍无新有效行） |
|---|---|---|
| 1 小时 | 10 分钟 | 20 分钟 |
| 2 小时 | 20 分钟 | 40 分钟 |
| 3 小时及以上 | 30 分钟 | 60 分钟 |

## 用现成脚本

实验只填参数，不新写观察脚本。脚本在本 skill 的 `scripts/`。

1. 任务结束时把退出码原子写到 `<log>.exit`；`remote-exec` 的启动模板已包含这一步。把 `watch.sh` 拷到日志所在机器，detach 后把 stdout 接到 `<log>.hb`：

```bash
bash watch.sh --log PATH --expect-secs SECS
```

2. 本地后台跑 `poll.sh`。它按同一间隔做短 SSH，只取 `.hb` 的新行。`notify_on_output` 匹配 `^(WATCH|HB|STALL|DEAD|RUN_ENDED|RUN_ERROR|WATCH_TIMEOUT) `。

```bash
bash poll.sh --ssh NODE --hb /remote/path.log.hb --expect-secs SECS
```

对用户只报变化：有效行变了、`STALL`、`DEAD`、结束或失败。同一句 `HB ... quiet` 不重复贴。

`STALL` 不杀任务。`DEAD` 且任务还在，只把 `watch.sh` 拉起来，不重启任务。

## 项目指标

最后一条有效日志不够时，用 `--metric-script PATH` 接一个项目自己的只读脚本。脚本每次执行只输出一行，如 `dumps=4`、`saved=12000`；这一行变化也算进度：

```bash
bash watch.sh ... --metric-script ./metric.sh
```

metric 脚本不循环、不 sleep、不改状态，也不重做通用的结束、超时和挂死判断。执行失败显示 `metric=unavailable`，不把任务判死。项目自己的成败条件由任务决定，并反映在 `<log>.exit`；不要把项目条件加进 `watch.sh`。

## 参数

| 参数 | 作用 |
|---|---|
| `--log` | 本次运行的新日志；对应退出码是 `<log>.exit` |
| `--expect-secs` | 预计时长；用于算心跳间隔，超时线是它的 2 倍 |
| `--metric-script` | 可选的项目指标脚本；输出变化也算进度 |

watcher 退出码：0 任务结束，1 任务失败，2 超过预计时长的 2 倍，3 日志不可读。

等 GPU、等端口就绪、checkpoint 出现后启动下一步，不是心跳，不要塞进这个脚本。
