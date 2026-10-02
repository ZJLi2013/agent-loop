# RoboTwin memory consolidation

## 结论

`episodes.md` 的问题不是文件达到硬上限，而是成功实验流水账、被覆盖状态和长期否定结论混在一起。
按 task / Goal CLOSE 语义收敛后，文件从 13.6 KB 降到 2.1 KB（−85%），同时保留所有会改变未来
选择的否定结论与证据入口。

## 收敛前

- `experiments` 按日期记录 exp5–46，重复项目文档中的过程与读数。
- `current decisions` 同时包含冻结、重开、再次停止及已过期的无人值守预算。
- 被证伪假设和否决方案埋在实验时间线里，检索容易被相邻成功记录挤掉。
- runtime 位于 legacy `.cursor/memory/`，并夹带一份未使用的 templates 副本。

## 收敛后

- `experiments` 只保留 3 条 task / Goal 级结论指针。
- `disproved` 保留 3 条会阻止错误归因或重复实验的结论。
- `rejected` 保留 3 条已停止的方案族。
- 当前状态、预算与排期回到 plan / `task.md`；原始读数继续由实验文档承担。
- 四个 memory 文件迁到 `.agent-loop/memory/`，legacy 文件与内嵌 templates 删除。
- `facts.md` 删除历史运行状态，只保留仍需复用的环境、身份、数据与模型入口；
  `lessons.md` 收敛到 15 条。

## 采用的边界

不增加后台清理器、容量截断或 Kernel state。`experiments > 10` 只作为 CLOSE 漏执行告警；
删除依据是“项目文档是否已承接、该条是否仍会改变未来选择”，不是日期。
