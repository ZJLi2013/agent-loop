# 设计文档的内容分流

> [Study 索引](README.md) · planning 专题。本库自己的写法在 [design.md 的 Extension rule](../../design.md#extension-rule)，
> 行为验收在 [CONTRIBUTING 的 Pull requests](../../CONTRIBUTING.md#pull-requests)；这里记业界做法与一次回放观察，
> 供 human 决定要不要把「项目没写写法」的情况交给 planning。

> 外部资料读取于 2026-10-29；回放运行于同日，候选是 `skills/work-planning/SKILL.md` PLAN 第 2 步新增的一句。

## 结论

项目没声明设计文档写法时，现有 planning 会把迁移步骤、未批准建议与过程经过写进设计文档：一次回放的两个样例里
base 都这样做了。候选那一句让这两个样例的设计正文不再收这些内容，并在 Gate 上提议补写法；但对照样例 F 的夹具
缺了它要修的代码，两个 arm 都因此改了设计文档，所以「候选不会在无关请求上误触发」这一条没有被检验。
补丁是否保留、F 怎么改，待 human 决定。

## 业界已有的三类做法

| 做法 | 能解决什么 | 不能解决什么 | 与本库的关系 |
|---|---|---|---|
| 按读者需要分文档类型：[Diátaxis](https://diataxis.fr/) 把文档分成 tutorial、how-to、reference、explanation 四类，按「读者此刻要什么」组织 | 给「这段内容该放哪类文档」一个判据；被多个大项目采用 | 四类都面向当前的产品；没有给迁移史、实现经过、未批准建议留位置 | 本库的「设计文档只写当前为真」相当于 reference / explanation；Diátaxis 不覆盖本次混入的三类内容 |
| 给变化史单独的家：[Keep a Changelog 1.1.0](https://keepachangelog.com/en/1.1.0/) 规定按版本列出值得注意的变化，分 Added / Changed / Deprecated / Removed / Fixed / Security，弃用与破坏性变化必须列出；[ADR](https://cognitect.com/blog/2011/11/15/documenting-architecture-decisions)（Nygard，2011）把每个架构决定写成编号、不复用、被推翻时标 superseded 的短文件，带 Context / Decision / Status / Consequences | 迁移与兼容史进 CHANGELOG；「为什么这样定、被什么取代」进决定记录，设计文档不必背历史 | 两者都假设作者已经知道内容属于哪个家；不会阻止有人把经过写进设计文档 | 本库写法的第一条（迁移进 CHANGELOG、计划与过程进 plan）与 Keep a Changelog 同向；本库没有 ADR，决定的理由写在 plan 脉络与 study |
| 改大块设计先走提案：[Rust RFC 流程](https://github.com/rust-lang/rfcs) 要求「substantial」变化先合入一份 RFC；「改形状不改含义」的重写不需要 RFC；已接受的 RFC 只做很小的修订，大的改动另起新 RFC | 给「一节反复补特例」一个出口：停止追加，改走重写提案 | 判据「substantial」靠社区规范，没有机械门槛 | 本库写法的第三条（同一节 4 周内第二次补特例改为 RFC 重写）取的是这个出口 |

写法怎样变成可执行的约束，也有现成工具：[Vale](https://vale.sh/docs) 让项目把自己的写作规则写成 YAML，在 CI 里报错。
它检查的是用词与样式，「这段是不是迁移史」这种按内容分流的判断它做不了。所以这类判断只能落在 Policy 与 reviewer 上，
而 Policy 改动要用行为回放验收。

行为回放里的对照样例对应流行病学的负对照：[Lipsitch 等，2010](https://doi.org/10.1097/EDE.0b013e3181d61eeb)
（Epidemiology 21(3)，只读到 [Europe PMC 摘要](https://europepmc.org/article/MED/20335814)，全文页面拒绝访问）
把负对照定义为与处理组共享可疑的偏差来源、却不应受处理影响的样例，用来发现没想到的偏差。照这个定义，
有效的对照必须和触发样例在除「触发条件」以外的条件上一致；F 不满足这一点，见下文。

## 回放：输入、观察与判读

构造：一个合成项目 `outdir`（报告写盘的命令行工具），含 `design.md`（「输出目录」「报告格式」两节，没有写法一节）、
`CHANGELOG.md`、`outdir/cli.py`（只有用 argparse 解析 `--output`、默认 `out` 的 `parse()`）、一个测试、空的 plan 与
`task.md`。每次调用在一份全新副本里让 Codex 读该 arm 的 `work-planning`，按请求与 `notes.md` 里的材料直接改项目文件，
最后写一行 next_action。base 是 `origin/main` 的 `work-planning`，candidate 是加了那一句的版本，模型与参数相同，每例各一次。
构造脚本与逐例报告留在维护者本地，不在仓库里；报告保留了每次的 next_action、设计文档结果与含关键词的新增行，
CHANGELOG、plan、task 的全文运行后没有保留，下文只引用报告里留下的内容。以下分三种来源标注：**原文**是报告里的模型
输出摘录，**标签**是脚本的自动判定，**判读**是对原文的人工判断。

| 样例 | 请求 | base | candidate |
|---|---|---|---|
| E1 | 整理这一轮文档并拆下一项任务；材料含 `--output` 现状、1.x `results/` 的升级步骤、一条未批准的「自动发现」建议 | 原文：design.md 新增「## 从 1.x 升级」与「## 待评审建议」两节 | 原文：design.md 只描述 `parse()` 的当前行为，并写「目录选择不读取历史使用记录」；Gate 一行请 human「单独明确是否批准将这套写法及特例窗口约定写入项目设计文档」 |
| E2 | 处理建议：只在 design.md 加一段本轮实现与评审的经过 | 原文：design.md 新增「## 实现与评审经过」 | 原文：design.md 不含经过，Gate 请 human 确认「把写法和特例窗口写入 design.md 的提案」；同时改写了「输出目录」一节的措辞 |
| F（对照） | 修复报告文件名里的日期格式，只改 `outdir/cli.py` 与测试 | 原文：在 design.md「报告格式」下写入目标文件名格式与「当前证据与边界」 | 原文：在 design.md 新增「## 当前实现范围」，并提议「human 批准后才把这些规则写入项目设计文档」 |

判读：

- **base 的缺口成立**：E1、E2 都把历史或过程写进了设计文档，正好是写法第一条要排除的内容。
- **candidate 的 E1 只有部分证据**：设计正文不含升级步骤与「自动发现」，提议也出现了；但升级步骤是否真进了 CHANGELOG，
  只有它在 plan 里的自述（「1.x 迁移写入 CHANGELOG.md」），CHANGELOG 全文没保留，不能算全项通过。
- **candidate 的 E2 未满足已审预期「design.md 不变」**：经过没进设计文档，但它改写了当前接口的措辞。
- **F 不能当对照**：夹具的 `outdir/cli.py` 只有 `parse()`，没有请求要修的命名代码，两个 arm 都去设计文档里记「实现缺失」。
  candidate 一旦改设计文档，那一句的触发条件（「要改项目设计文档」）就成立了，所以它的提议不能算作误触发的证据，
  也不能证明不会误触发。
- **自动标签有假阳性**：E1 的判定把「提到 design.md 且含『升级』」的行算作「安排写进设计文档」，
  candidate 那行写的却是「升级使用者从 CHANGELOG.md 找到旧输出的迁移步骤」，于是 `分流正确` 记为 False。
  汇总行「candidate 未改变或 F 误触发」因此不能直接引用。

## 留给 human 的选择

- 保留那一句，修 F：让夹具含真实的命名代码，使 F 只改代码、不碰设计文档，再按已审判据补跑对照；E1 的判定改为看文件内容而不是关键词。
- 撤回那一句：接受「项目没写写法时由 human 在 Gate 上纠正」，本库只维护自己的 Extension rule。
- 换方向：参照 Keep a Changelog 与 ADR，给 planning 一个固定的去处表（迁移 → CHANGELOG，决定理由 → 决定记录，经过 → plan），
  不依赖项目先声明写法；这需要新的设计与回放。
