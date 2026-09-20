---
name: code-review
description: >-
  Reviews a PR or diff: four-section output order, severity taxonomy (correctness >
  hot-path performance > maintainability > style > process), and AI-generated /
  vibe-coding detection. The review *standard* comes from the target repo
  (.cursor/BUGBOT.md, AGENTS.md, CONTRIBUTING.md) rather than from this skill.
  Use when reviewing a pull request or diff, or when the user mentions P0-P4 or
  vibe coding. Owns how a human-readable review is written; hand off to Cursor's
  review-bugbot / review-security subagents for automated bug and vuln sweeps,
  and to upstream-contribute for whether to open an upstream PR.
disable-model-invocation: true
---

# Code Review

## 先确定标准从哪来

**不要默认套用本 skill 附带的标准。** 按这个顺序找被审 repo 自己的标准，找到第一个就用它：

| 顺序 | 来源 |
|---|---|
| 1 | `.cursor/BUGBOT.md`（含从改动文件向上遍历找到的嵌套文件） |
| 2 | `AGENTS.md` / `CLAUDE.md` / `.cursor/rules/` |
| 3 | `CONTRIBUTING.md` 的 style / review 段 |
| 4 | 都没有 → [reference.md](reference.md) 的 P0–P4，**并在 review 开头声明用的是这套外部默认值** |

`reference.md` 是 [sglang-diffusion-routing#32](https://github.com/zhaochenyang20/sglang-diffusion-routing/issues/32)
的标准，面向高性能推理系统。审 Web 服务、CLI、文档仓库时它的 P1 整段不适用，别硬套。

> **仓库标准要影响 PR 上真正跑的那次 review，只能写进 `.cursor/BUGBOT.md` 或 dashboard 的
> Team / Repository Rules。** Bugbot 不读 `.cursor/rules/*.mdc`，也不读 Skills——
> 把规则放在那两处之外等于没配。

## 输出顺序（四段，不可打乱）

### 1. PR Summary & Technical Background

写清改动在系统里动了什么机制（梯度流、memory layout、同步、CUDA kernel、分布式通信、attention、KV cache、speculative decoding、TP），再判断：**必要且有依据**，还是在解伪问题、重复已有实现、或引入不必要复杂度。

### 2. Code Quality & Correctness

逐行审 diff。每条问题带严重度、引用规则、说明 WHY、给具体改法。严重度按下面的轴排序，标签名跟随上面选定的那套标准（`reference.md` 用 `[P0-BLOCKER]`…`[P4-PROCESS]`，Bugbot 用 Important / Nit）：

| 轴 | 管什么 |
|---|---|
| 正确性 | 竞态、off-by-one、shape/dtype、泄漏、over-catch、over-protect、缺 guard |
| 热路径性能 | host-device sync、GPU 数据走 Python、`.item()`/`.cpu()`/`.tolist()`、无谓分配 |
| 可维护性 | DRY、过长函数/文件、命名、import 顺序、魔法数、循环 import |
| 风格 | 非纯函数、动态属性、缺 type hint、分支不完整、debug 残留 |
| 流程 | 缺测试、缺可复制验证脚本、非确定测试 |

找不到问题就写清**为什么这段代码够格**，禁止空的 LGTM。

### 3. Goal Completeness

对照 PR 描述：实现是否覆盖声明目标、漏了哪些生产会炸的边角、未写明的假设、相对目标过工程或欠工程。

### 4. AI-Generated Code Detection

直接写是否像 vibe coding（贴了但没理解/没验）。信号：与仓库风格不合的样板、从不发生的边角上的过度防御、解释显而易见却漏掉域约束的注释、大块 `try/except`、无谓 null/fallback、能跑但看不出为何能跑、混用命名、仓库里没有的抽象、无视本系统约束的教科书实现。

## 什么时候不用本 skill

| 要的东西 | 用 |
|---|---|
| 自动扫 bug / 回归，要的是发现而不是评审文字 | Cursor 内置 `review-bugbot` subagent |
| 注入、认证、密钥泄漏这类安全面 | Cursor 内置 `review-security` subagent |
| 改动太大，先拆成可审的小 PR | Cursor 内置 `split-to-prs` |
| PR 建好之后跟 review comments 与 CI | Cursor 内置 `autopilot` |
| 该不该往上游提、body 怎么写 | `upstream-contribute` |

**本 skill 的独有价值是第 1 段与第 4 段**——判断这个改动该不该存在，以及它是不是没被理解就贴上来的。纯找 bug 交给上面那两个 subagent 更快。

## 行为约束

- 正确性与性能优先于 cleverness。
- 每条意见教 WHY + 正确做法；不抠不影响正确性/可维护性的格式。
- 先理解系统不变量再评；孤立看起来错、在不变量下正确的，按后者写。
- nit 要设上限。散文与配置能抛光到无穷，超过 5 条就归并成一句计数放进 summary。
