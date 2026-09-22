
# Agent Loop 设计沿革

> 当前架构以 [`design.md`](../design.md) 为准；本文保留问题背景与演进依据。

## 背景

当前工作范式： `人 → agent → 一个实验 → 人判断 → agent → 下一个实验`

预期：`Goal → Plan → Execute → Observe → Diagnose → Repair / Re-plan → Verify → Continue → Done`


### Anthropic Ralpha Loop

核心是一个orchestration primitive: `agent 想退出 → harness 判断 completion criteria → 没完成 → 把任务重新喂进去 → 新 iteration 继续`


###  [Karpathy/autoresearch](https://github.com/karpathy/autoresearch)

把 agent 工作压缩成一个非常明确的 closed-loop optimization problem。如果 crash 是 typo / missing import 这种简单问题，就自己修；如果 experiment 本身坏了，就记录并跳过，然后继续。**failure 是 input，不是 termination condition**，



## agent_loop 架构

### 它实际在管什么

这个环的主题不是编排，是**每一步判断该继续、该换一条、还是该停，并且默认继续**。
它同时压着两个相反方向：不轻易停（自修、跳过、无人值守），也不乱跑（只有一行 doing、检查点判据、中止清单）。

### 形状

```text
                  ┌──────────────────────────────────┐
                  │  常驻层：7 条 rule，每轮都在上下文  │
                  │  调度器必须在这里，不能是 skill     │
                  └────────────────┬─────────────────┘
                                   │
  GOAL ─► PLAN ─► HUMAN REVIEW ─► SELECT ─► DESIGN ─► EXECUTE ─► EVALUATE
   │       │          │              │         │                    │
 user    work-     proposed       task-state experiment-       ┌─────┴─────┐
  定     planning  approve/revise               design        pass        fail
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
  横穿全环：.agent-loop/memory/（值第二次用到就写，要用就读）
            agent-heartbeat（命令 > 60s）
            Harness（显式命令 timeout / journal；stop 前独立 Verify）
  环之外：code-review / upstream-contribute / research-to-blog /
          code-to-kernel-diagram / remote-exec —— user 明确要了才走
```

### 五个让它能自己转下去且不偏离 human 意图的机制

**一、调度器是常驻 rule。** rule 每轮都在上下文；skill 只有 name 与 description
在，正文要被语义匹配命中才加载。

**二、失败先分类再决定问不问人。** 六类各有去向与重试上限（`when-to-stop`）：
连不上先验事实、环境错误自修 2 次、契约不匹配回层 0、**假设被推翻算结果不算故障**、
判据失效退回任务指标、都用尽才查中止清单。重试必须换做法，原样重跑不算一次。

**三、防漂移靠不变量，不靠提醒。** `task.md` 里有且只有一行 `🔬 doing`，一次改动属于它的唯一
判据是「会让那行的验收检查点从不通过变成通过吗」。

**四、计划先过 Human Review Gate。** plan document 先承载 human 意图，新 task 先标
`📝 proposed`；批准前不进实验。无人值守时才按 KISS 自批准并标 `⚠️ unreviewed`。

**五、计划按 evidence 渐进展开。** 一个 task 最多跨越一个未验证假设，只细化最近 1–2 项；
每项变绿后重排。human 纠偏时 Harness 先 pause，plan revision 递增，再 RECONCILE `task.md`；
plan review、task `rN` 与 runtime revision 一致后才能 resume。


### 缺口

| 环节 | 现状 |
|---|---|
| OBSERVE | **没有独立节点**。实验类由 `experiment-design` 的 Phase 2/3 覆盖，重构 / 修 bug 类的产物无人要求落盘 |
| VERIFY | ✅ 锁定 verifier 独立执行；工作树 fingerprint 防止验证后改码 |
| 强制执行 | ⚠️ enforced adapter 能拒绝未验证的完成；未显式交给 runner 的 host tool call 仍由宿主管理 |


## 三层分工

| 层 | 职责 | 在本库是什么 |
|---|---|---|
| Agent | think / plan / execute / diagnose / replan | `agent-loop` 的路由 + 各格的 skill |
| **Harness** | run / timeout / retry / rollback / checkpoint / persist state / capture logs / resource limits | `harness/` + stop hook；checkpoint 复用 git |
| Verifier | 这件事真的做完了吗：实验回答了那个问题吗、指标动了吗、测试过了吗、证据够吗 | 锁定命令 + 输出契约 + fingerprint |


### Harness 的边界

| 能力 | 现状 |
|---|---|
| persist state | ✅ `task.md` + `.agent-loop/memory/` + `progress.md` |
| capture logs | ✅ runner 记录有界 stdout/stderr、hash 与 `runs.jsonl` |
| retry | ✅ Verify attempt 硬上限；repair 动作仍由 agent 选择，不原样自动重跑 |
| resource limits | ✅ runner 的总 wall budget；其它 host tool call 不在边界内 |
| timeout | ✅ runner 杀进程树；其它 host tool call 由宿主管理 |
| mid-run human review | ✅ pause request 可中断 runner；Plan Revision gate 拒绝旧 task 恢复 |
| run / rollback / checkpoint | ⚠️ run 已有；checkpoint / rollback 复用 git，不自动覆盖用户工作树 |


### Verifier

验收检查点写成初始化时锁定的命令；Harness 独立执行并保存证据。`exit 0` 之外可配置
`expect_regex` / `forbid_regex`，挡住「0 tests」这类假通过；验证后工作树变化会使证据失效。
stop hook 对未验证状态返回 `followup_message`，预算耗尽时只续一轮 Auto-Stop Report。


### 不做：task/hypothesis graph

`task.md` 是扁平列表 + `blocked-by` 链，**链长 ≥ 2 就停下问人**——这个上限是刻意的，
套两层说明最初的拆解不对。改成图会让嵌套变廉价，恰好鼓励了要防的那件事。

假设之间的依赖也没复杂到需要遍历，`episodes.md` 的 `#disproved` 与 `#rejected` 两个扁平
清单够用。等真被扁平结构卡住再说。



## GPT Insights

当前 agent-loop 是 task-centric agent, 而autoresearch 的关键是 evidence-centric agent.

下一步升级可以考虑，从 `SELECT -> next task` 到 `SELECT -> next best action`，这个action 可以是 a new experiment, inspection, write code, memory retreival, replanning, or ask human 等。









## 参考

* [ralph](https://github.com/chrismdp/ralph)
*
