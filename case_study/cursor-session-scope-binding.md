# Case：Cursor 会话绑错子项目，completion gate 查错对象，还被别的会话的锁打断

> 时间：2026-10-14。执行：Cursor 里的 Claude（agent-loop rules + Harness hooks）。同一 workspace
> `robot_rl_from_zero_to_expert` 下有多个子项目各自带 `.agent-loop/` 与 `.harness/`。本文记录问题，待修。

## 结论

**completion gate 这一整天检查的都不是正在推进的项目。** 会话绑定按"第一次读到的 `task.md`"一次定终身。
这个会话 08:38 读到 wm_forge 的 `task.md` 后就绑在了 wm_forge 上，之后的工作全部转到 robotRSI，绑定没有跟着变：

- **漏检**：robotRSI c2 一直处于 `active / running`，从没被 gate 检查过；wm_forge 已经是 `stopped`，gate 每次都直接放行；
- **误报**：21:19 另一个会话给 wm_forge 跑 plan-review，拿着 `.harness/lock` 两分钟左右。这个会话正好在那时结束，gate 抢锁失败，报出与当前工作无关的
  `Harness completion gate failed: ...wm_forge\.harness\lock exists; another run may be active`。

- **越权写状态**：次日 07:28 本会话再次结束时，wm_forge 里另一个会话的 u10 正处于 active，距上次 goal review 已过 35325 s。gate 直接把 u10 写成 paused，并对本会话报"Harness paused u10 for Goal Review"。u10 不是本会话的任务，本会话也无权替它做 goal review。

只看报错会以为是锁的问题。真正的问题是 gate 查错了对象：误报还会被人看见，漏检却悄无声息，越权写还会改掉别人的状态。

## 现场

| 时间（UTC+8） | 事件 |
|---|---|
| 08:38 | 会话读到 `wm_forge/.agent-loop/task.md`（做 WorldLoop PPT 时读 wm_forge 结果），scope 文件写入 wm_forge |
| 白天 | 工作转到 robotRSI：v0–v1、c1、c2 都在 robotRSI 的 Harness 下 `init` / `exec` / `verify` |
| 21:19:41 | 另一个会话执行 `plan-review --plan-doc upstream/bwm-robotwin-recipe/u10-aligned-seed.md`（wm_forge），持有锁并调用 WSL reviewer |
| 21:21 | 本会话结束，stop hook 对 wm_forge 跑 `completion_gate`，抢锁失败，报错 |
| 21:24 | wm_forge 的锁已释放；scope 文件仍指向 wm_forge |
| 次日 07:28:41 | 本会话结束，gate 对 wm_forge 的 u10（另一个会话 13:30 init，active）判定 goal review 到期，写入 pause；同一秒内 wm_forge 的状态以 `active=false, phase=stopped` 落盘（那边的 human 已决定暂停 u10，Harness 已 disable） |

两个项目当时的 Harness 状态：wm_forge `w32 active=False phase=stopped`，robotRSI `c2 active=True phase=running`。

## 机制漏洞

### 1. 绑定先到先得，不随工作迁移

- `adapters/cursor/session_scope.py:48–83`：`bind` 一开头就查 `roots(payload)`，已有绑定就直接返回；scope 文件以 `open("x")` 写入，只写一次。
- `tests/test_cursor_session_scope.py:55–69` 把这一点钉成了预期：同一会话再读第二个项目的 `task.md`，仍返回第一个。
- `adapters/cursor/hooks/harness-stop.py:22`：stop 只检查 `roots(payload)`，也就是这一个绑定的项目。同一 workspace 下其它带 `🔬 doing` 的项目都不在检查范围内。

后果是 gate 可以静默失效：只要会话最早碰到的是一个已停止的项目，之后无论在哪个项目里执行、验证，完成声明都不会被拦。

### 2. gate 用独占锁，且不等待

- `harness/core.py:521–525`：`completion_gate` 进入 `state_lock(root)`；
- `harness/storage.py:56–64`：`state_lock` 用 `O_CREAT | O_EXCL` 抢锁，已存在就立刻抛 `HarnessError`，不等待、不区分锁的持有者是否还活着；
- `harness/plan_review.py:177–218`：`plan-review` 在调用 reviewer 子进程的整个过程中都拿着锁，一次 1.5–2 分钟；
- `adapters/core.py:180–183`：stop hook 把这个异常原样包成"completion gate failed"，交给 agent 作为 followup。

所以只要别的会话在同一项目里跑一次 review，这个时间窗里结束的任何会话都会收到一条 gate 失败。agent 无从判断该等待、修复，还是忽略。

### 3. gate 会改写任务状态，却不知道任务属于哪个会话

- `harness/core.py:565–577`：goal review 到期时，gate 调用 `schedule_goal_review`，转移到 `paused` 并写回 `state.json`；`:590–600`（证据过期）与 `:620–625`（把 running 判为 interrupted）也都会写状态；
- `state.json` 没有记录哪个会话 init 了这个任务。任何绑定到该项目的会话一结束，都会以自己的名义推进别人的状态机；
- goal review 的到期按墙钟计算（`35325s since review`），所以一个闲置十小时的会话，结束时同样会触发。收到消息的会话并不在做这个任务，只能忽略，或者越权替别人做 goal review。

### 4. 已验证的 task 也会被拉去 goal review

2026-10-15 在 agent-loop 自身复现。t44 于 10-14 22:10 已 verified，reviewer 选 `continue → t45`；次日 09:22，
一个只读了 `task.md` 的会话结束，gate 报 `Harness paused t44 for Goal Review: goal_review_due: 40928s since review`。

- `harness/core.py:566–577`：goal review 计时排在 `:580` 的 `VERIFIED` 分支之前，已完成的 task 闲置超过 60 分钟就会被写成 `paused`；
- `adapters/core.py:138–150`：COMPACT 写 goal review pause 时也不看 phase；
- 照提示执行 `goal-review --decision continue`，`harness/attention.py:89–103` 会把它转回 `ready` 并清掉 `verified_fingerprint`，
  gate 随后要求为一个已关闭的 task 重跑 verifier。

Goal Review 管的是 task 内的下一动作；已验证 task 的下一步属于 reviewer 或 human，不该进这个检查。

## 修复（待实施）

| 漏洞 | 建议 | 状态 |
|---|---|---|
| 绑定不随工作迁移 | 绑定改为"最近一次 `init` / `exec` / `verify` 的 `--root`"或"最近读到的 `task.md`"；或 stop 扫描会话期间触达过的所有项目，凡 `active` 的都检查 | 未实施（t49：绑定会话读过 `task.md` 的每个项目） |
| 绑定可以静默指向已停止的项目 | gate 在绑定项目 `active=False`、同 workspace 内另有 `active` 项目时给出提示，而不是直接放行 | 不做：要扫描 workspace，与 lifecycle hook 不扫描其它项目的不变量冲突；t49 的触达集合已覆盖本例 |
| gate 抢锁即失败 | gate 只读 `state.json`，不进独占锁；需要写状态时短暂重试。锁文件里已有 pid，抢锁失败时可报告持有者是谁、在做什么 | 未实施（t50） |
| review 期间长时间持锁 | `plan-review` 只在读写 record 时持锁，调用 reviewer 子进程期间释放；并发安全交给 record 去重与工作区指纹 | 未实施（t51） |
| gate 越权写别人的状态 | `init` 把 conversation_id 记进 `state.json`；gate 只对自己 init 的任务写状态、发 followup，对其它会话的任务最多只读提示 | 已实施（[#27](https://github.com/ZJLi2013/agent-loop/pull/27)）：owner 取自 CLI 环境里的会话 id；别的会话的 task 不写、不提示 |
| 报错不可操作 | 锁冲突报成"项目 X 正被进程 N（plan-review …）占用，稍后重试"，与真正的 gate 失败区分开 | 未实施（t50） |
| 已验证的 task 被拉去 goal review | gate 在计时前处理 `VERIFIED`；COMPACT 跳过 `VERIFIED` 的项目 | 已实施（[#25](https://github.com/ZJLi2013/agent-loop/pull/25)） |

## worker 侧的教训

- gate 报错先看它指向哪个项目。报错路径不是当前工作的项目，就说明绑定错了，不能按字面去修锁。
- 不要删别人的锁。本例中那把锁属于一个正在运行的 plan-review，删掉会让对方的 review 记录失效。
- gate 安静不代表验证过了。会话跨项目工作时，要自己确认当前项目确实跑过 `verify`。

## 证据

- scope 文件：`%TEMP%\agent-loop-cursor-sessions\<sha256(conversation_id)>`，内容为 `...\wm_forge`，写入时间 08:38:44
- 锁持有进程：`python -c "...sys.argv=['agent-loop-harness','plan-review','--plan-doc','upstream/bwm-robotwin-recipe/u10-aligned-seed.md']..."`，21:19:41 启动
- `robot_rl_from_zero_to_expert/wm_forge/.harness/state.json`、`robot_rl_from_zero_to_expert/robotRSI/.harness/state.json`
