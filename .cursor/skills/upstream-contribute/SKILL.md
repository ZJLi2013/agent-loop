---
name: upstream-contribute
description: >-
  实验完成后自动评估是否值得向上游贡献 PR 或 Issue。读取 experiments.md 中的结论、
  修复列表、commit 记录，自主判断贡献类型，生成 PR/Issue body 供用户审查后手动提交。
  Use after experiment completion (experiments.md status changes to ✅),
  or when discussing contribution back to upstream repos.
disable-model-invocation: true
---

# Upstream Contribute — 实验结果 → GitHub PR / Issue

实验完成后，自动评估成果并生成上游贡献草稿。**不依赖 gh CLI**，生成 markdown body 供用户在浏览器中创建。

## ⚠️ 强制风险规避：GPU 型号脱敏

**所有对外内容（PR body、Issue body、commit message）中，必须将中国大陆特供 GPU 型号替换为北美对应版本号。**

| 大陆型号 | → 替换为 |
|----------|----------|
| MI308X | MI300X |
| MI308XHF | MI300X |
| MI308 | MI300 |
| MI258 | MI250X |
| MI210 | MI210 |
| MI108 | MI100 |

规则：
1. 实验文档 (`experiments.md`) 中可以保留真实型号
2. 生成 PR/Issue body 时**自动替换**，不需要用户提醒
3. Docker image tag、ROCm 版本号不受影响
4. 如果遇到未知的大陆型号，警告用户确认对应的北美型号

## ⚠️ 强制风险规避：AI 披露

见 `.cursor/rules/upstream-ai-disclosure.mdc`（always-applied）。与型号脱敏并列，同在跨出仓库边界那一刻生效。

## Step 1: 自动判断 — PR vs Issue vs 不做

实验结束后（experiments.md 状态 → ✅），agent **自主评估**：

| 条件 | → 动作 | 判断依据 |
|------|--------|----------|
| 有 fork 分支 + ≥2 处有意义的修复 + 端到端验证通过 | **PR** | 工作量值得 reviewer 花时间看 |
| 有 fork 分支 + 仅 1 处 trivial 修复（如改 flag）| **Issue** with patch | 太小不值得 PR 流程 |
| **无 fork** + 修复已验证 | **Issue** with inline diff/patch | 在 Issue body 中贴 diff，让维护者自己合入 |
| 发现 bug 但修复在第三方库 | **Issue** on upstream | 无法直接提 PR |
| 改动太 hacky / 仅适用特定环境 | **不做** | 记录在 experiments.md 即可 |
| 改动跨多个 repo | **拆分** | 每个 repo 独立评估 |

判断完成后，向用户报告结论和理由，等待确认后进入 Step 2。

## Step 2: 收集素材

从 experiments.md 提取：
- **修复列表**：每个 fix 的根因、改动文件、commit hash
- **验证结果**：demo 输出、性能数据
- **环境信息**：GPU 型号（⚠️ 脱敏后）、ROCm 版本、Docker image

检查 fork 状态：
```bash
git -C <local_fork_path> log --oneline origin/<branch> -5
git -C <local_fork_path> remote -v
```

## Step 3: 生成 body — 等待用户审查

### PR body 模板

```markdown
## Summary

Enable <project> to run on AMD GPUs (ROCm/HIP).

### Changes
- <one-line per fix, link root cause>

### Tested on
- GPU: AMD Instinct <脱敏后型号>
- ROCm: <version>
- PyTorch: <version>
- Docker: `<image tag>`

### Results
<key metrics: timing, output verification>

### Notes
- All changes are backward-compatible with CUDA
- <any caveats>
```

### Issue body 模板

```markdown
## Problem

<one paragraph: what fails, on what platform>

## Reproduction

\`\`\`bash
<minimal repro steps>
\`\`\`

## Root Cause

<brief analysis>

## Suggested Fix

<patch or description; omit if none>

## Environment
- GPU: AMD Instinct <脱敏后型号>
- ROCm: <version>
- PyTorch: <version>
```

### 输出方式

生成完整 markdown body 后：
1. 输出 PR/Issue **title** 和 **body**
2. 提供上游 repo URL（如 `https://github.com/Luo-Yihao/FaithC/compare/main...ZJLi2013:rocm_support`）
3. 用户复制到浏览器创建

## 多 repo 拆分

当改动跨多个 repo 时：

1. 按 repo 分别生成 PR/Issue body
2. body 中互相引用（`Related: <owner>/<repo>#<num>`）
3. 先提依赖库的，再提主项目的
4. 如果依赖库 PR 未合入，主项目 body 中说明 workaround

## 原则

- **简洁**：reviewer 能在 2 分钟内理解全部改动
- **向后兼容**：强调不影响 CUDA 用户（`try/except` fallback 等）
- **可验证**：提供复现命令
- **脱敏**：对外内容无大陆特供型号

## 与其他 Skill 的协作

- **experiment-driven-doc**: PR/Issue 素材来源
- **split-to-prs**: 大改动拆分成多个小 PR
- **babysit**: PR 创建后持续跟进 review comments 和 CI
