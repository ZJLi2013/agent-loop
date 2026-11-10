# 暂停与恢复共用一份 task 判定

**推荐：`pause` 与 `resume` 调用 `harness/plan.py` 里同一个判定，适用条件跟 `init` 按计划核对 task 行一致：只在 Harness 绑定了
计划时要求当前 task 在 `task.md` 中且未关闭。** 这样 `pause` 接受过的暂停，`resume` 在 task 状态未变时一定能清掉；
`--require-revision` 不走这个判定。

#177 的首个修复（PR #183）在 `request_pause` 里加了第二份检查，条件与 `resume` 不同，留下两种 `pause` 拒绝而 `resume` 本可
通过的情形，见 [纠偏与 Goal Review](../usage.md#纠偏与-goal-review)。本文给出对照依据与补充修正方案。

## 两种公开实现

读取日期 2026-11-10，只读源码，未实测。

| 实现 | 暂停前检查 | 恢复前检查 | 两者关系 |
|---|---|---|---|
| kubectl `rollout pause` / `rollout resume` | 对象是支持的 Deployment 类型，且未暂停（[objectpauser.go](https://github.com/kubernetes/kubectl/blob/64cedd4e35cdaf9045ec5599282bd1c4198aedb0/pkg/polymorphichelpers/objectpauser.go#L32-L64)） | 同一组类型，且已暂停（[objectresumer.go](https://github.com/kubernetes/kubectl/blob/64cedd4e35cdaf9045ec5599282bd1c4198aedb0/pkg/polymorphichelpers/objectresumer.go#L31-L63)） | 可操作的对象集合相同，状态检查互补；集合在两个文件里各写一遍 |
| Argo Workflows `suspend` / `resume` | 已完成的 workflow 拒绝（[util.go](https://github.com/argoproj/argo-workflows/blob/45e810c8f15eec84c13c3a3e9d8dc6d14b97d068/workflow/util/util.go#L480-L491)） | 不查完成状态，有 `spec.suspend` 就清掉（[util.go](https://github.com/argoproj/argo-workflows/blob/45e810c8f15eec84c13c3a3e9d8dc6d14b97d068/workflow/util/util.go#L541-L545)） | 恢复的接受范围宽于暂停，暂停接受过的一定能恢复 |

两者共同保证的是：**暂停成功后，恢复不会因为同一个前提而失败。** kubectl 靠两边同一组类型，Argo 靠恢复不设更严的前提。
#183 之前的 agent-loop 两条都不满足，#177 的卡死由此而来。

## 推荐

- 判定只有一份，归 `harness/plan.py`：返回拒绝理由或 `None`，`request_pause`（非 `--require-revision`）与 `resume`
  （非纠偏暂停）都在改状态之前调用它，消息相同。
- 适用条件取 `init` 的：绑定了计划（`plan_revision` 非空）时，当前 task 必须在 `records.open_task_ids` 里；没绑定计划时不查。
  `init` 只在绑定计划时按计划核对 task 行，没有计划的首次 `init` 不要求 task 在 `task.md` 里，`pause` 也就不该要求；
  这去掉了 #183 对「有 `task.md`、没有计划」项目的兼容变化。
- `resume` 遇到判定拒绝（暂停后 task 被关闭，或旧版本写下的暂停）时报同一条理由，并指出用 `init` 开后继 task；
  `init` 会清掉残留的 `pause.json`（2026-11-10 在一次真实运行里观察到）。不让 `resume` 静默删暂停。
- 采用 kubectl 的「同一集合」而不取 Argo 的「恢复更宽」：agent-loop 的 `resume` 之后紧跟 plan review 与执行，放行一个已关闭的
  task 会让后面的步骤在错的 task 上跑。

## 不适用

- Argo 的恢复不设前提：agent-loop 恢复后会重新执行，已关闭 task 不应被恢复执行。
- kubectl 把类型集合在两处各写一遍：这正是 #183 的形态，不照搬。
- 让 `pause` 跟 `resume` 一样只在配置了 reviewer 时检查：没有 reviewer 但绑定了计划的项目，`init` 已要求 task 行，暂停也该要求。

## 补充修正怎么做与验收

- 在 #183 保留的 auto-fix worktree（分支 `auto-fix/177`）里交给 Codex 一次，输入是本文的推荐与 issue；不重跑
  `.github/auto-fix/run.ps1`，不改 `.github/auto-fix/`，不手写代码。
- 在现有三个提交之后追加三个：回归测试（CI 在新测试上失败）、修复（CI 通过）、撤测（CI 通过）。#183 原来的三个提交与 head
  `29f61af` 留作已验收证据。
- 回归测试覆盖：绑定计划时，已关闭仍在表里与已归档的 task 都拒绝 `pause` 且不写 `pause.json`；没绑定计划、有 `task.md` 而 task
  不在表里时 `pause` 与 `resume` 都成功；`pause` 之后 task 被关闭，`resume` 报同一条理由；`--require-revision` 不受影响。
- 修复后核对 `harness/plan.py` 里只有一处判定被两条命令调用，并把 [纠偏与 Goal Review](../usage.md#纠偏与-goal-review) 与
  CHANGELOG 改成最终行为。
- 预算：human 2026-11-10 批准追加一次，主动工作最多 60 分钟；不通过则保留现场交 human，不再追加。
