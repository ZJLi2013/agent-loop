# agent-memory skill 精炼：去重，不改决定

> [Study 索引](../README.md) · 被改文件是 [`skills/agent-memory/SKILL.md`](../../../skills/agent-memory/SKILL.md)，
> 基线是 `7b5b346` 上的版本。

`agent-memory` 的 `SKILL.md` 从 138 行减到 113 行。改前列出的 19 条决策规则在新版里都能找到，
没有一条规则改变 agent 在任何输入下的动作。按 [CONTRIBUTING](../../../CONTRIBUTING.md#pull-requests)，
不改变决定的措辞改动不需要回放，所以本次只做了静态核对。本文记录做法与取舍，作为以后精炼 skill 的样本。

## 做法

1. 通读全文，按「同一条规则出现几次、出现在哪」找冗余，不按段落顺序找。
2. 动手前列出这份 skill 管的每一条决策规则（见下面「决策清单」），作为改后的核对表。
3. 搜索仓库里按节名或原句引用这份 skill 的地方。`docs/study/correction-replay.md` 按名字引用了「准入与上限」一节
   和 `[纠正]` 一句，所以这两处原样保留。
4. 每条规则只留一处陈述，删掉的副本不留指针。只陈述一次论证就够的，留在规则所在的那一节。
5. 回读 diff，逐条对决策清单；跑 `python -m unittest discover -s tests` 与 `git diff --check`。

## 冗余与处置

行号指基线版本。

| 冗余 | 原位置 | 处置 |
|---|---|---|
| INDEX 上限 30 行、超了会被忽略中段 | 第 31、45、88 行 | 只留在「收敛」一节；代码块注释只写数字 |
| 索引常驻、内容定向读 | description、第 85–86、134 行 | 留 description 与「收敛」首句 |
| 「删一条排除项，三周后有人重提」 | 第 72、96 行 | 只留在写入表 |
| episodes 收敛规则 | 写入表 `task → ✅` 行（第 70 行）、老化表（第 93–96 行）、consolidation 段（第 100–112 行） | 老化表并成两条清单，`task → ✅` 行只说写哪儿，收敛四步不变 |
| 两节都讲上限 | 「上限落在哪一层」「准入与上限」 | 前者改名「收敛：只有索引有上限」，只管 INDEX 与 episodes；后者只管 facts 与 lessons，节名不变 |
| Retrieval hints 的情境清单 | 第 60–61 行，与 `templates/INDEX.md` 重复 | 删清单，指向模板 |
| 「不做检索」整节 | 第 132–136 行 | 压成「读」一节里的一句 |
| 失败多半是事实过期的论证 | 第 130 行，与 `when-to-stop` 失败表首行重复 | 删论证，留验证动作 |
| 设计辩护与实现细节 | 开头动机段（第 12–16 行）、第 65 行「和『我是不是漂了』同一类毛病」、第 49 行 adapter 接线 | 动机压成两句；后两处删除，接线归 `design.md` 的 adapter 表 |

## 保留且不算冗余

- 写入表整张，包括「不写会怎样」一列：每行是一条独立的写入规则，后一列是它唯一的理由。
- 「`INDEX.md` 最要紧」一句：它是常驻索引存在的理由，全文只说一次。
- 旧 `.cursor/memory/` 与工作树内 `.agent-loop/memory/` 的迁移说明：hook 仍发这条告警，文档要解释它。
- `[纠正]` 条目的晋升流程：只在宿主没有决策日志时生效，删掉会让这类宿主失去规则。

## 决策清单

改前列出、改后逐条核对，每条都在新版里有且只有一处：

1. 范围：值、结论、教训；任务状态归 `task-state`，实验过程归 `experiment-design`，procedural 归 `skills/`。
2. 存放位置：每个 clone 一份，工作树共用；非 git 项目与 monorepo 子项目用 `.agent-loop/memory/`；不写空 `.git/`。
3. 初始化：拷模板、删示例；hook 按 cwd 解析。
4. 共用工作树：只对一方成立的事实写范围，改前重读、局部修改。
5. 旧位置：合并后删除，不双写。
6. INDEX 只放「有什么 + 在哪」，带 anchor。
7. hook 在读 `task.md` 时注入；查询取 Goal 行与 `🔬 doing` 行；命中为空报库存条数。
8. hook 覆盖不到时按 Retrieval hints 先读。
9. 定向读取，不用 embedding、向量库或 FTS。
10. 写入表九行。
11. 写内容与更新 INDEX 是一个动作。
12. INDEX 超 30 行时并粗条目，不删条目。
13. episodes 不设统一行数上限；`disproved` / `rejected` 不老化。
14. 收敛判据是「是否还会改变未来选择」；原始 evidence 不复制进 memory。
15. CLOSE 收敛四步。
16. `experiments` 超 10 条是告警、不按日期删；`current decisions` 不是合法小节。
17. facts 准入两条件与排除项。
18. lessons 上限 15 条与 `[x1]`–`[x3]` 晋升；`[纠正]` 走起草、reviewer、PR。
19. 新 session 与连接类失败时验证要用的 facts，不对就覆盖。

## 没做的

- 跨文件重复只改了本文件这一侧：`when-to-stop` 失败表与 `task-state` 交接一节仍各自陈述「先验 facts」。
- 没做行为回放。若要证明精炼不改变行为，可用同一组场景（读 `task.md` 后的检索、task CLOSE 时的收敛、
  INDEX 超限）在基线与新版各跑一次，比较 agent 的动作。

## 验证

- `python -m unittest discover -s tests`：175 个测试通过。
- `git diff --check`：无输出。
