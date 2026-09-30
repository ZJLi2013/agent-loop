# Case：agent-loop 自身的跨 session 记录增长

> 迁移于 2026-10-01，Plan Revision 8 / t9。

## 结论

迁移前，agent-loop 已能把长期 memory 按需检索，却会让已完成 task 继续进入每次 SELECT。
t9 把 closed task 移到 linked archive 后，活跃 `task.md` 从估算 2,347 字符降到 1,198 字符，
默认上下文减少 49%；t22、t24、t25、t26 的四条完整验收仍可从 archive 定向读取。

这验证了 consolidation 的有效判据：**新 session 默认只看到当前状态，旧证据仍可定向找回。**
本仓库没有 `progress.md`，交接快照的覆盖 / 归档规则只完成了 Policy 验证，没有伪造迁移数据。

## 迭代事实

2026-09-20 至 09-30 的提交依次覆盖：

- project memory 与强制检索 hook；
- Windows BOM 导致 hook 静默失效的修复；
- plan revision、pause gate 与 verifier；
- Stable Kernel / Policies / Adapters 分层；
- task-boundary reviewer；
- pager 与 reviewer 自动调用。

这些不是同一 task 的连续调参，而是多次 Goal 细化和架构修改。仓库因此同时包含“当前设计”和
“如何走到这里”的记录。

## 迁移前暴露的问题

### `task.md`：历史 task 每次都进入上下文

`.agent-loop/task.md` 是 SELECT 必读文件。t22、t24、t25、t26 已完成，但仍和 t7、t8、t9、
t23 一起整表加载。done 行对审计有用，对选择下一 task 没有直接作用。

合适的活跃面只需要：

- proposed / todo / doing / blocked；
- 最近一个完成项及其 evidence 指针；
- 指向 done-task archive 的链接。

### `episodes.md`：检索成本受控，内容生命周期仍不完整

`INDEX.md` 常驻，`episodes.md` 只返回词面命中的少量条目，所以它没有被每个 session 全量加载。
这层设计是有效的。

问题在于 `experiments` 仍采用追加模式，只有 Goal 关闭且结论已收口后才允许人工剪除。
相反，`disproved / rejected` 是高价值长期决定，应继续保留。两类记录不能用同一个行数上限处理。

### `design.md`：当前架构与迭代依据混在同一活跃文档

`design.md` 已是 as-built 的真相源，但也保留了多轮需求形成的依据。新 task 通常只需要当前 Goal、
当前结论、下一步决策和相关 contract；历史路线应通过 case study、commit 或 archive 定向进入。

### `progress.md`：本仓库尚未使用，但模板会产生同类增长

当前仓库没有 `.agent-loop/progress.md`，因此不能把“progress 已膨胀”当成观察结果。不过
`task-state` 规定它按时间戳追加；长期项目若每个 session 都写交接，旧的“下一步第一条命令”
会与当前接手点并存。

更合适的结构是：

```text
progress.md                 # 覆盖：当前唯一接手快照
archive/progress-YYYY-MM.md # 追加：历史交接，仅按需读取
```

## 迁移结果

下一位 agent 开始后续 task 时，默认上下文只有：

1. 当前项目 Goal 与 plan revision；
2. active task 的检查点和状态；
3. 当前架构结论；
4. 命中的 memory，特别是已有的 rejected / disproved 决定；
5. 一个 closed-task archive 指针。

t22–t26 的逐项验收已从活跃表移到 `.agent-loop/archive/tasks.md`。迁移后测量：

| 指标 | 迁移前 | 迁移后 |
|---|---:|---:|
| active `task.md` 估算字符数 | 2,347 | 1,198 |
| 默认加载的 closed-task 明细 | 4 | 0 |
| archive 中可追溯的 closed task | 0 | 4 |

迁移没有删原始证据；case study、Git history、Harness artifacts 与 archive 继续承担追责和复现。
`task.md` 仍出现 t22–t26 的短指针，这是索引，不是完整验收记录。

通用生命周期与开源实践见
[`study/experiment-record-lifecycle.md`](../study/experiment-record-lifecycle.md)。
