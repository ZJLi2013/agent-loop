# agent-loop Tasks

## Goal

把这个库从「一堆被动调用的 skill」变成一个会自己往前走的 agent loop：
遇到非预期情况先自修，只在真该问人的时候停。

| P | id | task | 验收检查点 | 状态 | 失败 |
|---|---|---|---|---|---|
| P1 | t7 | memory hook 加第二个触发点 | 不读 task.md 的会话里也能拿到 INDEX | ⬜ todo | 0 |
| P1 | t10 | 项目级与 user 级 hook 去重 | 本仓库里读 task.md 只注入一份 Memory | ⬜ todo | 0 |
| P1 | t8 | VERIFY：识别假通过 | 能挡住 skip 掉的测试与坏掉的 baseline | ⬜ todo | 0 |
| P2 | t9 | CONSOLIDATE 与清理触发点 | `[x3]` 提示晋升；已关闭 feature 的 experiments 行被提示剪掉 | ⬜ todo | 0 |
| — | t1 | skill 去重与归属表 | 16 → 10，无重复归属 | ✅ done | 0 |
| — | t2 | 调度器改成常驻 rule | `agent-loop` 每轮在上下文 | ✅ done | 0 |
| — | t3 | 漂移不变量 | 只有一行 `🔬 doing` | ✅ done | 0 |
| — | t4 | 无人值守模式 | 触发词能翻转三个开关 | ✅ done | 0 |
| — | t5 | memory v1 | hook 能注入 INDEX 与命中 | ✅ done | 0 |
| — | t6 | 全局同步一条命令 | `sync-to-cursor.ps1` 幂等 | ✅ done | 0 |

<!-- 一行一个 task。范围、方案、分析写在它链接的文档里，不写在这儿。
     结论与排除项进 .cursor/memory/episodes.md。 -->
