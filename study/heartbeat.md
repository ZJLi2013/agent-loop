# 心跳

> 2026-10 对照三份社区做法。执行契约在 [`skills/agent-heartbeat`](../skills/agent-heartbeat/SKILL.md)，这里只记取舍。

## 结论

三份都把「进程还在」和「还在往下做」拆开。本库取了输出增量、连续两拍、以及挂了必须打出一行；不取杀进程，也不取它们的固定秒数。

## 输出增长才是进度

[subagent-watchdog](https://github.com/npow/claude-skills/blob/main/_shared/subagent-watchdog.md) 把运行时的 `status: running` 标成弱信号：它只说明 pid 还在任务表里，死锁、空转、卡在重试里都是这个状态。它认的进度是输出文件的 mtime / 字节增长。看不了这个文件时，它要求判成异常，不能判成健康。

本库同一条：最后一条有效日志变了才是 `HB ... alive`，任务终态只认启动器原子写下的 `<log>.exit`。日志连续两拍读不到是 `DEAD`。

没取它的处置。它在安静超过 `HUNG_THRESHOLD`（默认 30 分钟）时 `TaskStop` 掉子任务。它的默认节拍是 STALE 10 分钟、HUNG 30 分钟、轮询 60 秒，本库的间隔由预计时长算，不沿用这组常数。

## 连续两拍无增量才算挂

[long-run-watchdog](https://github.com/merceralex397-collab/skilllibrary/blob/main/05-agentic-orchestration-and-autonomy/long-run-watchdog/SKILL.md) 先定一个进度量（新文件、通过的测试、新增的输出行），再拿这一拍和上一拍比。增量为 0 连续两拍，标记 `STALLED`。日志根本读不到时，它直接当挂住，不再等。

本库同一条：一拍没有新的有效行只打 `HB ... quiet`，第二拍才打 `STALL`。读不到日志走 `DEAD`。总超时是预计时长的 2 倍，量级和它「没有进度量就退回 wall-clock、阈值 2 倍预计时长」一致。

没取它的默认间隔（短任务 60 秒、长任务 300 秒），也没取它后面的重启、循环检测和资源暴走处置。

## 挂了要留下一行，然后停手

[stallguard](https://github.com/blockhaven-ai/stallguard) 针对的是同一件事：systemd / launchd 只看得见进程死了，看不见活着但停工。它在超时后一定打出一行，带上沉默秒数、最后一次匹配的内容和 pid，`--quiet` 也压不住。

本库的 `STALL` 同样带 `quiet=` 和最后一条有效行。

没取它的后半段：对整个进程组先 SIGTERM 再 SIGKILL，退出码 124，还可以按指数退避重启。训练任务被观察脚本杀掉，比晚一拍发现挂住更贵。

还有一处判据不同。stallguard 的 `--expect` 是任意一行匹配就重置计时，同一句反复刷也算活。本库要求有效行发生变化；只刷 Warning 或重复同一行，两拍之后是 `STALL`。它另外提醒：stdout 进管道后变成块缓冲，心跳会晚到，看起来像挂。本库读的是任务自己写下的日志，任务不 flush 时会同样误报。

## 项目指标只留接口

实际实验还会用 dump 数、checkpoint step、样本数等指标判断进度。它们不进入通用 watcher：项目提供一个单次执行、只输出一行的 metric 脚本，`watch.sh --metric-script` 把指标变化和有效日志变化等价看待。项目脚本不负责循环、间隔或挂死处置。

这条边界保留了 `_watch.sh` 里的 `dump=N`，同时避免每个实验复制一遍观察循环。GPU 占用不默认算进度：GPU 忙不等于任务在推进；确实需要时由项目 metric 显式输出。
