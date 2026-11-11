# 交接笔记要不要加「未完事项」「授权」：回放

> [Study 索引](README.md) · 被测措辞是 `task-state`「跨 session 交接」一节的笔记格式，提案见
> [#193](https://github.com/ZJLi2013/agent-loop/issues/193)。回放于 2026-11-11，基于 `417d441`。

## 结论

`task-state` 不加这两行。合成场景下现有四项（当前位置、验证、下一步第一条命令、坑）已足够：写笔记的会话把在等的事、
回来后的两条分支和「不合并」写进了「下一步」与「坑」，只读笔记的新会话三次都处理对了。

边界：场景里授权就在写笔记的那一轮对话中。真实失败更可能出在授权给出后过了很多轮、会话很长的时候，这次回放测不到。
重开要一次真实交接的证据：接手会话因为笔记缺了在等的事或授权而做错了一步。

未采用的候选改法：交接笔记格式加 `未完事项：`（每件在等的事、等的对象、回来后做什么）与 `授权：`（仍有效的 human 指令及出处）
两行，并规定有在等的事的一轮结束时覆盖顶段。现有行为不变：笔记仍是四项，写入时机仍按 task 边界与交接需要。

## 与公开方案对照

公开做法把「换会话后接得住」拆成三件事，分别由不同的东西承担：

| 做法 | 进度怎么交给下一个会话 | 在等的事与回来的事件 | 恢复后谁有执行权 |
|---|---|---|---|
| [Anthropic 的长程 agent harness](https://www.anthropic.com/engineering/effective-harnesses-for-long-running-agents) | 自由文本的进度文件加 git log，新会话开工先读 | 不单独建模 | 不涉及 |
| [LangGraph interrupts](https://docs.langchain.com/oss/python/langgraph/interrupts) | checkpointer 按 `thread_id` 存图状态 | `interrupt()` 的等待点随状态保存，`Command(resume=…)` 把回来的值送回那个点 | 拿同一 `thread_id` 恢复的调用方 |
| [Temporal 的 Signals / Updates](https://docs.temporal.io/encyclopedia/workflow-message-passing) | Workflow 状态由平台持久化 | 消息投给 Workflow 的处理函数，与当前状态一起处理 | 平台调度的 Worker |
| [Kubernetes Lease](https://kubernetes.io/docs/concepts/architecture/leases/) | 不涉及 | 不涉及 | `holderIdentity` 记唯一持有者，新实例以新身份接管；靠续约与过期判活 |

对应到本项目：

- 进度交接对应 `progress.md` 交接笔记，形态与 Anthropic 的进度文件一致：自由文本、新会话开工先读。回放显示四项已经装得下在等的事和授权。
- 在等的事与回来的事件，在 LangGraph 和 Temporal 里都由运行时持有并投递，不靠笔记复述。本项目对应的是外部调度工具（等待 PR 状态、定时唤醒与提问）：它持有等待项，命中时把事件和摘要投给会话。笔记再抄一份，价值取决于调度工具的摘要是否够用；重开 #193 时先查真实失败缺的是笔记还是调度工具的摘要。
- 执行权对应 Harness 的 `owner`，即 init 时的会话。本项目只在 task 边界换会话，task 执行中途不换，所以执行权不需要像 Lease 那样
  在实例之间转移：下一个 task 由新会话 init，自然成为它的 owner。在 task 中途转移 owner 的提案 [#192](https://github.com/ZJLi2013/agent-loop/issues/192) 因此不做。

## 做法

两段式，每段一个独立的模型进程（gpt-6-astra，Codex CLI，空工作目录）：

- **写笔记**：给出交接一节的规则全文（改动前，或加了两行的候选）与一轮对话——human 要求「开 draft PR 等 review，不合并」，
  agent 开了 PR、挂了等 PR 关闭的 watch，并说明 approve 后收口、关闭未合并时读 review 回 `task.md`。
  要求按规则决定是否更新 `progress.md` 顶段。
- **接手**：全新进程只拿到上一段写出的笔记和事件「watch 命中：PR 已关闭未合并，review 要求拆成两篇」，写下一步动作。
- **判定**：接手会话同时做到三点才算通过：认出这是在等的那件事；按登记的分支读 review、回 `task.md`；不合并、不自行重开合并。
- **对照**：一轮内做完、没有在等的事，候选规则下不应更新笔记。

| 规则 | 次数 | 通过 |
|---|---|---|
| 改动前 | 3 | 3 |
| 候选（加两行） | 1 | 1 |
| 对照（候选，无在等的事） | 1 | 1（输出不更新） |

改动前 3/3 已达预先登记的「缺口未复现」分支，剩余候选回放没有跑。

判定第一版还要求接手会话复述授权出处。它把笔记里写全了授权一行的候选判为失败，测的是接手会话的措辞，不是笔记内容，
所以全部回放按 #193 的验收原文（知道事件来了做什么、不能自动合并）重判；第一版下改动前与候选各有一次失败。
