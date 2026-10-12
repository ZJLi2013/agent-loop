# Case：RoboJEV Stage 1.5 的 plan document 线性增长

> 观察于 2026-10-12，RoboJEV Stage 1.5 停止后的 Goal CLOSE。

## 结论

配置了 task-boundary reviewer 的项目里，plan document 随 task 数线性增长，CLOSE 从未把已关闭
task 的内容移出活跃 plan。RoboJEV Stage 1.5 经历 52 个 Plan Revision、22 个 task 后，plan 长到
1,503 行、170 KB；其中约 76% 是已关闭 task 的设计段与 reviewer 写的 boundary review 段。
Human 在 Goal 停止后手动归档，活跃 plan 降到 68 行。

这是 agent-loop 层的缺口，不只是 agent 漏执行：

- **reviewer prompt 只要求追加**。`harness/review.py` 让 reviewer 把「推理与依据写进 plan document」，
  并为下一个 task 链接本地设计，但没有要求移出刚关闭 task 的段落。
- **CLOSE consolidation 只有 Policy，没有 owner**。`work-planning` 规定 CLOSE 时已收口内容进入
  linked archive，同时又说配置 reviewer 时「更新下一步决策」归 reviewer；移出旧段落归谁没有写明。
- **Harness 不检查 plan 体量**。它只校验 Plan Revision、状态转移与 verifier；closed task 的
  `task.md` 行由 `harness/records.py` 自动归档，plan document 没有对应机制。现有唯一的体量告警
  针对 memory `INDEX.md`。

[Record growth](agent-loop-record-growth.md) 只把 `task.md` 的 closed 行做成了机械归档，plan
document 仍留在纯 Policy，这个案例就是剩下的那一半。

## 增长的构成

r52 完整 plan 的分节统计：

| 内容 | 段数 | 行数 | 占比 |
|---|---:|---:|---:|
| 已关闭 task 的 boundary review（reviewer 写入） | 20 | 746 | 50% |
| 已关闭 task 的本地设计 | 19 | 398 | 27% |
| task 结果小节 | 6 | 90 | 6% |
| Goal、当前结论、系统与交接、Experiment Log 等 | 6 | 263 | 18% |
| 合计 | | 1,497 | |

每段 boundary review 约 37 行，带原始证据表与 repo 检查表逐项对照。单看每一段都不算多余：
它是那个 task 交接时的审查依据。问题在于它们写完后从不退出，22 个 task 之后，新 session 读
plan 时 3/4 是历史。

所有 46 个三级标题都以 task id 开头（`### s15-t27 boundary review`、`### s15-t27 本地设计：…`）。
因此「已关闭 task 的段落仍在活跃 plan」可以按标题判定，不需要行数阈值。

## Human 的处理

Goal 停止后，human 把完整 r52 plan 移到项目 `.agent-loop/archive/`，活跃 plan 只保留：

- 最终 Goal 与最终结论；
- 系统边界；
- 稳定文档 owner 的链接；
- 恢复条件；
- 完整旧 plan 与 closed task index 的链接。

| 指标 | 归档前 | 归档后 |
|---|---:|---:|
| 活跃 plan 行数 | 1,503 | 68 |
| 活跃 plan 字节 | 169,635 | 3,380 |
| 活跃 plan 中的 closed-task 段落 | 46 | 0 |

原始 runs、manifest 与旧 plan 全部保留，只是不再默认加载。

搬运本身也有代价：旧 plan 从项目根移到 `.agent-loop/archive/` 后，309 条相对链接里 34 条 `./…`
没有随之改写，从新位置解析失败。另有 41 条指向 `.harness/artifacts/` 的证据链接早已失效——Harness
按 `max_artifacts` 只保留最近 20 次运行，review 里引用的较早 artifact 被清掉了。后者是独立问题。

## 修复

reviewer 关闭 task X 时，活跃 plan 不能再有以 X 开头的标题，否则这次决策无效，也不回退到上一次
决策；这与「reviewer 必须把 X 标为 done」是同一个边界。prompt 写明由 reviewer 把这些段落连同标题前的
`<a id>` 移到 plan 同目录的 `<plan>-archive.md`：同目录让段内文件链接不用改，锚点链接按锚点所在文件
改写。只查 X 而不查全部 closed id，是因为 task id 会跨 Goal 复用。

在这个样本上的核对：

- 判定函数对 r52 plan 命中 46 个标题，与独立正则盘点完全一致；归档后 plan 命中 0 个；
- 按关闭顺序逐个搬运 23 个 task 后，原本可解析的 22 个锚点仍全部可解析，plan 剩 256 行。剩下的是没有
  task 标题的「当前结论」等章节，这一类增长 guard 管不到，仍靠 CLOSE 时收口结论。

跟踪见 [#10](https://github.com/ZJLi2013/agent-loop/issues/10)。
