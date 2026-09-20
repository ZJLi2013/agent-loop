---
name: code-review
description: >-
  Reviews PRs and diffs with the sglang-diffusion-routing four-section template
  and P0-P4 style guide (correctness, GPU hot-path performance, maintainability,
  style, process), including AI-generated / vibe-coding detection.
  Use when reviewing pull requests, doing code review, applying that repo's
  code style, or when the user mentions P0-P4, vibe coding, or
  sglang-diffusion-routing review.
  Owns review comments; upstream-contribute owns whether/how to open an upstream PR.
disable-model-invocation: true
---

# Code Review（sglang-diffusion-routing）

按 [Issue #32](https://github.com/zhaochenyang20/sglang-diffusion-routing/issues/32) 的模板写评审。
P0–P4 细则见 [reference.md](reference.md)。本 skill 只管评审意见；提上游 PR/Issue 走 `upstream-contribute`。

## 输出顺序（四段，不可打乱）

### 1. PR Summary & Technical Background

写清改动在系统里动了什么机制（例如梯度流、memory layout、同步、CUDA kernel、分布式通信、attention、KV cache、speculative decoding、TP），再判断：**必要且有依据**，还是在解伪问题、重复已有实现、或引入不必要复杂度。

### 2. Code Quality & Correctness

逐行审 diff。每条问题带严重度标签、引用规则、说明 WHY、给具体改法：

| 标签 | 管什么 |
|------|--------|
| `[P0-BLOCKER]` | 正确性：竞态、off-by-one、shape/dtype、泄漏、over-catch、over-protect、缺 guard |
| `[P1-PERF]` | 热路径：host-device sync、GPU 数据走 Python、`.item()`/`.cpu()`/`.tolist()`、无谓分配 |
| `[P2-MAINTAIN]` | DRY、过长函数/文件、命名、import 顺序、魔法数、循环 import |
| `[P3-STYLE]` | 非纯函数、动态属性、缺 type hint、分支不完整、debug 注释残留 |
| `[P4-PROCESS]` | 缺测试、缺可复制验证脚本、非确定测试 |

找不到问题就写清**为什么这段代码够格**，禁止空的 LGTM。

### 3. Goal Completeness

对照 PR 描述：实现是否覆盖声明目标、漏了哪些生产会炸的边角、未写明的假设、相对目标过工程或欠工程。

### 4. AI-Generated Code Detection

直接写是否像 vibe coding（贴了但没理解/没验）。信号：与仓库风格不合的样板、从不发生的边角上的过度防御、解释显而易见却漏掉域约束的注释、大块 `try/except`、无谓 null/fallback、能跑但看不出为何能跑、混用命名、仓库里没有的抽象、无视本系统约束的教科书实现。

## 行为约束

- 正确性与性能优先于 cleverness。
- 每条意见教 WHY + 正确做法；不抠不影响正确性/可维护性的格式。
- 先理解系统不变量再评；孤立看起来错、在不变量下正确的，按后者写。
