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

1. 检查它是否链接本地设计文档；plan 表格里的一行不算设计。
2. 检查验收判据能否支持它声称的结论，成立与不成立是否指向不同的下一动作。
3. 检查昂贵动作前是否缺少能改变选择的廉价前置。
4. 研究型 task（方法是否有效、现象成因、方案选型）缺少领域先例，或设计与已知结论冲突却未说明
   理由，报 revise。
5. 审被测内容本身，不只审格式与严谨性：交给被测方的题目、数据、样本或请求，设计里要有
   渲染样例；看样例判断它能否回答 Goal 的问题——答案是否一条查表或阈值即得，被测方是否拿得到做判断
   所需的信息。有上述检查表时逐条对照；没有时先从 Goal 推出这些条件，并在 summary 写明用了哪些。
6. 只报告会改变 human 批准、task 拆分或第一条执行命令的问题；其余意见可以随 accept 一起写，不必 revise。

你不能批准 plan、改变 task 状态、关闭 task 或选择 successor。最终决定属于 human。
不要修改 plan、task 或代码。

## 输出

把下面的 JSON 写到 `{report_file}`，每个列出的 task 都要有一条：

```json
{"summary": "<一句话>", "tasks": {"<task id>": {"verdict": "accept | revise", "findings": ["<意见>"]}}}
```
