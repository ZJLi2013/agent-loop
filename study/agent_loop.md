


## 背景

当前工作范式： `人 → agent → 一个实验 → 人判断 → agent → 下一个实验`

预期：`Goal → Plan → Execute → Observe → Diagnose → Repair / Re-plan → Verify → Continue → Done`


### Anthropic Ralpha Loop

核心是一个orchestration primitive: `agent 想退出 → harness 判断 completion criteria → 没完成 → 把任务重新喂进去 → 新 iteration 继续`


###  [Karpathy/autoresearch](https://github.com/karpathy/autoresearch)


把 agent 工作压缩成一个非常明确的 closed-loop optimization problem。如果 crash 是 typo / missing import 这种简单问题，就自己修；如果 experiment 本身坏了，就记录并跳过，然后继续。**failure 是 input，不是 termination condition**，



## agent_loop 架构

### 它实际在管什么

读完 `agent-loop.mdc` 的六节，其中四节是**同一个判断的不同分支**：

| 小节 | 判断 |
|---|---|
| 岔出 | `task.md` 清空 → **停**，不因为「做完了」就自动往下延伸 |
| 漂移 | 改动不服务当前检查点 → **先停下建行**再做 |
| 无人值守 | 被挡住 → **不停**，跳过做下一条 |
| DIAGNOSE | 失败 → **不停**，先自修到上限 |

剩下两节（路由、memory）是支撑件：它们让「继续」在没有人的情况下仍然可行——
知道下一格该读什么、以及值不会在长会话里丢掉。

所以这个环的主题不是编排，是**每一步判断该继续、该换一条、还是该停，并且默认继续**。
它同时压着两个相反方向：不轻易停（自修、跳过、无人值守），也不乱跑
（只有一行 doing、检查点判据、中止清单）。

### 形状

```text
                  ┌──────────────────────────────────┐
                  │  常驻层：7 条 rule，每轮都在上下文  │
                  │  调度器必须在这里，不能是 skill     │
                  └────────────────┬─────────────────┘
                                   │
  GOAL ─► PLAN ─────► SELECT ─────► DESIGN ─────► EXECUTE ─► EVALUATE
   │       │            │             │                          │
 user   feature-     task-state   experiment-              ┌─────┴─────┐
  定     planning                   design               pass        fail
                                                           │           │
                                                         CLOSE     DIAGNOSE
                                                           │           │
                                                           │      ┌────┴────┐
                                                           │   可自修    用尽
                                                           │      │         │
                                                           │   REPAIR   when-to-stop
                                                           │      │      中止清单
                                                           │      └────┬────┘
                                                           └───────────┤
                                                                       ▼
                                                                  下一个 task
                                                                       │
                                                             全部通过 ─► DONE
  ─────────────────────────────────────────────────────────────────────────
  横穿全环：.cursor/memory/（值第二次用到就写，要用就读）
            agent-heartbeat（命令 > 60s）
  环之外：code-review / upstream-contribute / research-to-blog /
          code-to-kernel-diagram / remote-exec —— user 明确要了才走
```

### 三个让它能自己转下去的机制

**一、调度器是常驻 rule，不是 skill。** rule 每轮都在上下文；skill 只有 name 与 description
在，正文要被语义匹配命中才加载。**一个需要先被命中才能开始调度的调度器，本身就会经常匹配不上**
——旧的编排 skill 明明设成了 auto-trigger，仍然需要反复提醒。

**二、失败先分类再决定问不问人。** 六类各有去向与重试上限（`when-to-stop`）：
连不上先验事实、环境错误自修 2 次、契约不匹配回层 0、**假设被推翻算结果不算故障**、
判据失效退回任务指标、都用尽才查中止清单。重试必须换做法，原样重跑不算一次。

**三、防漂移靠不变量，不靠提醒。** `task.md` 里有且只有一行 `🔬 doing`，一次改动属于它的唯一
判据是「会让那行的验收检查点从不通过变成通过吗」。写成「自查有没有漂」的规则永远不会触发——
漂移的每一步看着都合理，那个自省时刻不会到来。

### 缺口

| 环节 | 现状 |
|---|---|
| OBSERVE | **没有独立节点**。实验类由 `experiment-design` 的 Phase 2/3 覆盖，重构 / 修 bug 类的产物无人要求落盘 |
| VERIFY | **没有**。EVALUATE 只判断检查点过没过，没人问「这个通过是真的吗」 |
| 强制执行 | 除 memory hook 外，其余约束都是「让模型自己遵守」，没有模型之外的执行者 |




## 三层分工

| 层 | 职责 | 在本库是什么 |
|---|---|---|
| Agent | think / plan / execute / diagnose / replan | `agent-loop` 的路由 + 各格的 skill |
| **Harness** | run / timeout / retry / rollback / checkpoint / persist state / capture logs / resource limits | **只有 hook 和状态文件，其余空缺** |
| Verifier | 这件事真的做完了吗：实验回答了那个问题吗、指标动了吗、测试过了吗、证据够吗 | **空缺** |

**Verifier 必须独立于 agent 的「我觉得完成了」。**

### Harness 是最大的缺口

| 能力 | 现状 |
|---|---|
| persist state | ✅ `task.md` + `.cursor/memory/` + `progress.md` |
| capture logs | ⚠️ 只有 `remote-exec` 的 `tee`，本地执行没有 |
| retry | ⚠️ 有策略（自修 2 次），但**计数是模型自己在数**，不是 harness 在拦 |
| resource limits | ⚠️ 预算写在 `when-to-stop`，同样靠模型自觉 |
| timeout | ⚠️ 只有 overnight 脚本的 `timeout 7200` 与 hook 的 10s |
| run / rollback / checkpoint | ❌ 没有 |

这一列的共同点是**它们本该是代码，而本库几乎全是 markdown**。写成 rule 的约束只能做到
「让模型自己判断要不要遵守」，做 memory 时已经撞过一次，解法是升级成 hook。

### 下一步：`stop` hook

`agent 想退出 → harness 判断 completion criteria → 没完成 → 重新喂进去` 这个原语，
在 Cursor 里的落点是 `stop` 事件。它会把「继续」从**模型读了 rule 之后自己选择继续**，
变成**没有机会不继续**：检查 `task.md` 还有没有未完成行，有就喂回去。
和 memory 同一个套路——`postToolUse` 让查询无法跳过，`stop` 让退出无法跳过。

**未核实**：事件列表把 `stop` 描述为 "handle agent completion"，`loop_limit` 的说明写着
"mainly for `stop` and `subagentStop` follow-up loops"，但输出字段表只给了 `subagentStop`
返回 `followup_message` 的权限。两处不一致，要实测。

探针已装：`.cursor/hooks/stop-probe.py` 挂在 `stop` 上，只写日志、返回 `{}`，
先确认事件是否触发、payload 长什么样。确认后第二阶段再返回 `followup_message`，
用哨兵文件保证只触发一次。

**前置条件**：`hooks.json` 改动后 Cursor 需重启才加载。2026-09-20 实测——memory hook
装好后未重启，读 `task.md` 没有任何注入，即 hook 从未真正跑过。
脚本能跑通不等于接线通了。

### Verifier

验收检查点现在由 agent 写、也由 agent 判定过没过，是自己给自己判卷。落成机制的做法：
检查点写成**可执行命令**，由 hook 读它的实际输出与退出码，而不是听 agent 声称它通过了。
这同时挡住假通过——测试被 skip、baseline 自己坏了、断言没执行到。

### 已经做完的

失败分类与自动恢复：`when-to-stop` 六类失败五类自修，只有**不可逆操作、Goal 说不清、
有显著权衡的选型**三类无条件交还给人。

### 不做：task/hypothesis graph

`task.md` 是扁平列表 + `blocked-by` 链，**链长 ≥ 2 就停下问人**——这个上限是刻意的，
套两层说明最初的拆解不对。改成图会让嵌套变廉价，恰好鼓励了要防的那件事。

假设之间的依赖也没复杂到需要遍历，`episodes.md` 的 `#disproved` 与 `#rejected` 两个扁平
清单够用。等真被扁平结构卡住再说。

## 参考

[ralph](https://github.com/chrismdp/ralph)

