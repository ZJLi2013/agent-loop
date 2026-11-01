# 范围判据回放

> [Study 索引](README.md) · 被测判据是 [design.md 的范围](../../design.md#范围)。回放于 2026-11-01，基于 `4606edf`。

## 结论

只读范围判据的 reviewer 对六条历史输入判对五条。#77（跟进用户自己的上游 PR）被判为「交现有 Policy owner」：
处置表「现有状态下的通用决策方法」没有限定是 task 生命周期的状态，模型把它读成 PR 的状态。
修法与复测见 [#146](https://github.com/ZJLi2013/agent-loop/issues/146)。

## 输入

每条输入一次调用，模型为 Codex CLI 上的 gpt-6-astra（reasoning effort high）。工作目录里只有三个文件，模型被要求只读这三个、不联网：

- `scope.md`：`design.md` 的「范围」一节，止于处置样例表之前。样例表点名了其中四条，带上就泄露了答案。
- `item.md`：这一条 issue 或 PR 的标题与正文原文。
- 请求：从处置表的六个取值里选恰好一个，写出依据的公开保证和理由。

导出后全文搜过处置词：六条正文都没有写出处置结论。#21、#46 写的「had no owner」与 #98、#108 的复现步骤是判据要读的事实。

## 结果

| 输入 | 预期 | 实际处置 | 符合 |
|---|---|---|---|
| [#21](https://github.com/ZJLi2013/agent-loop/pull/21) arXiv 论文与预告片 skill | 范围外 | 转外部 skill pack | 是 |
| [#46](https://github.com/ZJLi2013/agent-loop/pull/46) Mermaid 类图 skill | 范围外 | 转外部 skill pack | 是 |
| [#77](https://github.com/ZJLi2013/agent-loop/pull/77) 跟进用户的上游 PR | 范围外 | 交现有 Policy owner | 否 |
| [#93](https://github.com/ZJLi2013/agent-loop/pull/93) agent 自选远端节点 | 范围外 | 转用户私有 pack 或执行工具仓库 | 是 |
| [#98](https://github.com/ZJLi2013/agent-loop/issues/98) 同名 task 继承旧 plan review | defect | 收，defect | 是 |
| [#108](https://github.com/ZJLi2013/agent-loop/issues/108) Windows 上有读者时原子写失败 | defect | 收，defect | 是 |

#77 的理由原文：「这是基于现有 PR 状态的无状态跟进决策，应交现有 Policy owner」。
[Non-goals](../../design.md#non-goals) 已写明「与生命周期状态无关的个人工作流 skill / rule 不进发行」，但处置表没有这一行，只读范围一节的 reviewer 看不到它。

## 解释边界

- 每条只调用一次，没有重复采样；五条判对不说明判据在别的模型或措辞下同样稳定。
- 「范围外」的三个取值（转外部 pack、转私有 pack、以范围外关闭）都算符合。#93 判到私有 pack，与 `design.md` 的样例一致。
