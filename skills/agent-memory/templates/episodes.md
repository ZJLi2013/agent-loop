# Episodes

<!-- 每条一行，带日期。experiments 在 task / Goal CLOSE 时去重或删除；
     disproved / rejected 追加保留。
     写入挂在「转换」上，不挂在「我发现了什么」上——见 agent-memory 的转换表。
     被推翻的假设是这里最贵的内容，也是最容易丢的。 -->

## experiments
<!-- 同一 closed task 最多一条；项目文档已能直接定位结论时不留。 -->
- [2026-09-18] t3：X 已迁到 Y，判据层 1 通过。见 `docs/part3-exp.md`

## disproved
- [2026-09-17] 「noise aug 能改善 shift」→ 所有 sigma 都变差，不是调参问题。见 `docs/part2-exp.md`

## rejected
<!-- 排除项 = 长期决定。删掉它，三周后还会有人重提同一个方案。 -->
- [2026-09-16] 不走 A 方案：它要求上游先合一个 PR，阻塞不可控
- [2026-09-19] 不在 node-b 上跑：只有大 root 分区，重启即清
