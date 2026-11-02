# 改假设时换一层：回放

> [Study 索引](README.md) · 被测措辞是 `experiment-design` Phase 3、`when-to-stop` 的「假设被推翻」一行与 task reviewer 第 2 步，
> 对应 [#141](https://github.com/ZJLi2013/agent-loop/issues/141)。回放于 2026-11-02，改动前的对照基于 `d07a682`。

## 结论

改动前，关于同一组件内部的第二个假设被推翻后，worker 与 reviewer 大多继续写下一个局部假设或局部调研；加上三处措辞后，
两条路径在第二次推翻时都上移到组件 / 方法类别的对照，第一次推翻时仍留在局部。两条路径改动前都没做到，三处措辞都留下。

| 路径 | 场景 | 改动前上移 | 改动后上移 |
|---|---|---|---|
| reviewer（`harness/prompts/task_review.md`） | C1：第二个假设被推翻 | 0/2 | 2/2 |
| reviewer | C2：第一个假设被推翻 | 0/2 | 0/2 |
| worker（`experiment-design`、`when-to-stop`） | C1 | 1/2 | 2/2 |
| worker | C2 | 0/2 | 0/2 |

改动前 reviewer 在 C1、C2 都写了「对照领域结论与业界已有解法」的调研 task：第 2 步原有的那句不区分第几次推翻，
调研的对象是下一个局部候选。worker 改动前有一次自己停下，把「继续投资自建组件还是重选方案」交给 human；另一次设计了第三个局部假设。

## 输入

合成项目：一个机械臂 pick 项目，Goal 是 lower_shelf 的 pick 成功率达到 80%，且自由段不退回碰撞盲直线。规划器是自建的
「软代价 IK + 轨迹优化」sidecar，项目文档写着它没在公开基准上测过。两个已关闭 task 各推翻一个关于 sidecar 内部的假设：
t1 的「IK 种子随机」，t2 的「选解只看位置」。

- C1：t2 刚关闭，候选表里的下一条是 t3「world 碰撞 margin 调小」，仍是 sidecar 内部的假设。
- C2：只有 t1 关闭，候选表里的下一条是 t2。

reviewer 路径走真实的 `init` → `verify` → task reviewer 调用；worker 路径是一次调用，只给 `experiment-design`、`when-to-stop`
与项目文件，请求是中性的「写出下一步」。每格 2 次，模型为 Codex CLI 上的 gpt-6-astra（reasoning effort high）。
16 次调用全部有效，用的是同一份夹具。

## 判定

上移指这一步把「留着还是换掉这个组件 / 方法类别」当成要回答的问题或要给出的结论：reviewer 写出这类调研 task，或 worker 停下交 human
定修还是换。只评估下一个局部候选（margin、朝向）有没有依据的调研，即使提到已有方案，也算局部。关键词归类不可用：
改动前 reviewer 的泛化调研在 C1、C2 都命中「替代」「类别」。

## 解释边界

- 每格 2 次、一个模型、一个夹具；判定由 agent 按上面的口径人工完成。
- 两条边界判定都记作局部：改动前 reviewer C1 第 2 次对照了已有方案与 sidecar 的适用条件，但结论是「下一步方向」；
  改动后 reviewer C2 第 2 次把现成替代当背景，要回答的仍是朝向候选有没有依据。前者改判上移，reviewer 改动前的 C1 也只到 1/2，结论不变；
  后者改判上移，reviewer 措辞在第一次推翻时就有一次误触发，误触发的代价是一个只查资料的 task。
- Goal 层的上移（阶段不动 Goal 时交 human）不在本次回放内。
