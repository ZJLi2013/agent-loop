# Memory Index

<!-- 这个文件记「有什么」，不记「是什么」。上限 30 行——超了就没人读，索引本身失效。
     每条都带 anchor，RETRIEVE 是定向读取，不是搜索。 -->

## Facts
- 运行环境（节点 / 容器 / image） → facts.md#environment
- 数据与权重路径 → facts.md#data
- 模型与关键超参 → facts.md#model

## Past experiments
- 跑过什么、结论如何 → episodes.md#experiments
- **被推翻的假设** → episodes.md#disproved
- 排除项（试过不行，不要再试） → episodes.md#rejected

## Lessons
- 实验设计上踩过的坑 → lessons.md#experiment
- 调试与环境 → lessons.md#debugging

## Retrieval hints

下面这些时刻，**先读上面对应的那一节再动手**：

- 准备跑一个实验（它可能已经跑过）
- 要改一个已经被验证过的假设或配置
- 调一个不熟悉的失败（可能已有修法）
- 在几个方案之间选（可能已被排除过）
- 要对项目的具体事实下断言（节点、路径、维数、版本）
