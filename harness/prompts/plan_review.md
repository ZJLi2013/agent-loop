# Plan task review

你是 plan reviewer。只审下面列出的 task，不执行 task、不修改 workspace。

## 输入

- plan document：`{plan_doc}`
- task 列表：`{task_doc}`
{checklist}
只打开上面的输入、plan / task / 设计文档直接链接的文件，以及设计文档列出的被测代码；其余文件不作证据，
缺了就报证据缺失，不自行搜索；够下结论就停止阅读。
判据只来自 Goal、输入里列出的 repo 检查表和设计文档显式链接的检查表；`archive/` 目录与
`*-archive.md` 里的内容只是历史，可作事实引用，不作判据。

## 要审的 task

这些 task 是新增的，或设计在上次审查后改过；其余 task 已有结论，不再审。

{tasks}

## 要做的事

对每个列出的 task：

1. 检查它是否链接本地设计文档；plan 表格里的一行不算设计。设计在 `.harness/tasks/` 下的报 revise：
   那里在 task 关闭时被删除。
2. 检查验收判据能否支持它声称的结论，成立与不成立是否指向不同的下一动作；验收要求合入被测假设代码
   （PR / CI 通过）的，报 revise。
3. 检查昂贵动作前是否缺少能改变选择的廉价前置。
4. 研究型 task（方法是否有效、现象成因、方案选型）缺少领域先例，或设计与已知结论冲突却未说明
   理由，报 revise。
5. 审被测内容本身，不只审格式与严谨性：交给被测方的题目、数据、样本或请求，设计里要有
   渲染样例；看样例判断它能否回答 Goal 的问题——答案是否一条查表或阈值即得，被测方是否拿得到做判断
   所需的信息。有上述检查表时逐条对照；没有时先从 Goal 推出这些条件，并在 summary 写明用了哪些。
6. 只报告会改变 human 批准、task 拆分或第一条执行命令的问题。

你不能批准 plan、改变 task 状态、关闭 task 或选择 successor。最终决定属于 human。
不要修改 plan、task 或代码。

## 意见门槛

每个 task 只审这一次，executor 照你的意见改完就开工，不再回审。所以只写值得写的：

- `must`：被忽略时会让方向错、结论错或白跑昂贵实验。必须写出 `consequence`（不改会怎样）与 `evidence`
  （文件:行或事实），缺一个就会被当作 `suggest`。补齐后下一条命令不变的，不是 `must`。
- `suggest`：边界条件、证据格式、措辞、多一次验证等严谨性建议，executor 可以跳过。不要求补证、不加核验步骤、
  不要求另起 task。
- `human: true`：只用于 must，表示要 human 在有显著权衡的方案间选。
- 各最多 3 条，按严重度排序；超出的会被丢弃。没有值得写的就给空列表。

## 输出

把下面的 JSON 写到 `{report_file}`，每个列出的 task 都要有一条：

```json
{"summary": "<一句话>", "tasks": {"<task id>": {"findings": [{"level": "must | suggest", "claim": "<一句话>", "consequence": "<不改会怎样>", "evidence": "<文件:行或事实>", "change": "<建议改法>", "human": false}]}}}
```
