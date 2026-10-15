# Case：runner 被中止后锁不释放，远端作业照跑但 journal 是空的

> 时间：2026-10-14。执行：Cursor 里的 Claude（agent-loop Harness）。`harness exec` 通过 ssh 在远端节点跑一个
> 约 18 分钟的 CPU 探针（robotRSI c2）。本文记录问题，待修。

## 结论

**runner 进程一被宿主中止，就留下四个问题：锁永远不释放，状态机停在 `running`，远端作业继续跑完，这次运行在 journal 里只剩一个空目录。**
下一次 `exec` 先报"another run may be active"；手删陈旧锁后，又报 `run_started is invalid from running`。
agent 看到的是"命令启动失败"，以为什么都没跑；实际上远端已经把结果写完了。

## 现场

| 时间（UTC+8） | 事件 |
|---|---|
| 21:09:11 | `harness exec -- ssh <node> "... vla_swap_probe_c2.py ..."` 启动，runner pid 38928 写入 `.harness/lock`，建 `artifacts/20261014T130911Z-f9589e18/` |
| 21:09 | Cursor 把这次工具调用报成 `Command failed to spawn: Aborted`，pid 38928 被结束 |
| 21:09–21:27 | 远端探针继续运行，21:27 写出 `results.json`（2.4 MB） |
| 21:26 | 重新 `exec`，4 秒失败：`robotRSI\.harness\lock exists; another run may be active`。锁里的 pid 38928 已不存在 |
| 21:27 | 那次运行的 artifact 目录为空：没有 `result.json`、`stdout.log`、`stderr.log`，`runs.jsonl` 也没有记录 |
| 21:31 | 确认 pid 已死后手删锁，再 `exec`，3 秒失败：`run_started is invalid from running` |
| 21:32 | 用 `pause --reason ...` 加 `resume` 走 `running → paused → ready` 才恢复。CLI 没有直接表达"上一次运行已中止"的入口 |

## 机制漏洞

### 1. 锁不检查持有者是否还活着

- `harness/storage.py:56–71`：`state_lock` 用 `O_CREAT | O_EXCL` 建锁并写入 pid，释放只靠 `finally: unlink`。进程被强制结束时，`finally` 不执行；
- 抢锁失败时只看文件是否存在，不读 pid、不判断持有进程是否还活着、不看锁的年龄。死锁只能由人或 agent 手删。

### 2. exec 在整个命令期间持锁

- `harness/core.py:294` 进入 `state_lock`，`:386` 在锁内调用 `execute_process`。一次 55 分钟超时的命令，就要把项目锁拿 55 分钟；
- 同一项目在这段时间里的 `status`、`completion_gate`、`plan-review` 都会抢锁失败。
  [会话绑定那篇](cursor-session-scope-binding.md)里 gate 被 plan-review 的锁打断，是同一个根因。

### 3. 状态机停在 running，没有恢复入口

- `harness/protocol.py:46–51`：`RUN_STARTED` 进入 `running`，只有 `RUN_FINISHED` / `RUN_FAILED` 能离开。两者都由同一个 runner 进程在命令结束时触发；
- `protocol.py:61` 已经定义了 `INTERRUPTED: running → failed`，但没有任何代码路径在"上次 runner 已死"时触发它；
- 恢复只能借道 `pause` + `resume`，pause 原因要手写，journal 里看不出这是一次中止。

### 4. 被中止的运行没有痕迹，远端子进程变成孤儿

- 运行记录只在命令结束后写入：artifact 目录先建好，`result.json` 和日志最后落盘，`runs.jsonl` 最后追加。中途被杀，就只剩空目录；
- 本地 ssh 客户端死了，远端命令并不跟着停。Harness 不知道远端还有一个作业，结果文件出现时，它不属于任何一条 run 记录；
- 宿主报的是"spawn 失败"，agent 据此判断"没执行"，差点在同一输出目录上重跑，覆盖掉已经跑完的结果。

## 修复（待实施）

| 漏洞 | 建议 | 状态 |
|---|---|---|
| 死锁不自愈 | 抢锁失败时读 pid：进程不在就视为陈旧锁，记一条 `stale_lock_recovered` 后接管；进程还在就在报错里写出 pid、启动时间与命令 | 部分实施（t50）：报出持有者、持有者已不在时给出删锁命令；按 [#35](https://github.com/ZJLi2013/agent-loop/issues/35) 不自动回收 |
| exec 全程持锁 | 只在读写 `state.json` 与 journal 时短暂持锁；运行期间改用 `state.phase=running` 加 run_id 表示占用，第二个 `exec` 以"已有运行中的 run"拒绝 | 已实施（[#37](https://github.com/ZJLi2013/agent-loop/pull/37)） |
| 状态停在 running | 进入 `exec` / `verify` / gate 时，若 `phase=running` 而记录的 runner pid 已死，就触发已有的 `INTERRUPTED`，转成 `failed` 并记入 journal，之后按正常失败路径重试 | 已实施（t52）：本次 exec / verify 只报 aborted 不执行，下一次照常执行 |
| 中止的运行无痕迹 | 启动时先把 `{run_id, pid, argv, started_at}` 写进 artifact 和 `runs.jsonl`，日志流式写入；下次进入时发现 pid 已死、却没有结束记录，就补记 `outcome: aborted` | 部分实施（t52）：写 `start.json`、补记 aborted；按 human 选择不做日志流式写入 |
| 远端孤儿作业 | 文档要求远端长作业用 `agent-heartbeat` 的 detach + 日志模式，runner 只负责启动和轮询；或者 `ssh -t` 让远端随连接结束 | 未实施（t53：选 detach + 日志） |

## worker 侧的教训

- 宿主报"spawn 失败 / Aborted"，不等于命令没执行。先看锁里的 pid、artifact 目录，以及远端输出的修改时间，再决定是否重跑。
- 远端输出目录在重跑前先确认里面的内容是哪一次运行写的，避免覆盖一次已经完成的结果。

## 证据

均在 `robot_rl_from_zero_to_expert/robotRSI`：

- `.harness/lock`：内容 `38928`，写入时间 21:09:11；该 pid 已不存在
- `.harness/artifacts/20261014T130911Z-f9589e18/`：空目录
- 远端 `<workdir>/vla-c2/results.json`：节点本地时间 08:27（UTC 13:27）写出
