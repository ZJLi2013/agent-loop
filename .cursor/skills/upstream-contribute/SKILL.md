---
name: upstream-contribute
description: >-
  判断一个修复该提 PR、提 Issue 还是不提，并生成 body 草稿。目标 repo 有 PR 模板就用它的。
  Use when contributing a fix back to someone else's repo.
disable-model-invocation: true
---

# Upstream Contribute — 本地修复 → GitHub PR / Issue

评估在他人仓库里做出的修复值不值得提，并生成草稿。**不依赖 gh CLI**，生成 markdown body 供用户在浏览器中创建。

**开写 body 之前先过 `external-output-boundary`**（always-applied rule）：AI 披露段、GPU 型号脱敏表、
私料清理清单都在那里，本 skill 不重述。下面只管「提不提」和「body 长什么样」。

## Step 1: 自动判断 — PR vs Issue vs 不做

修复验证通过后，agent **自主评估**：

| 条件 | → 动作 | 判断依据 |
|------|--------|----------|
| 有 fork 分支 + ≥2 处有意义的修复 + 端到端验证通过 | **PR** | 工作量值得 reviewer 花时间看 |
| 有 fork 分支 + 仅 1 处 trivial 修复（如改 flag）| **Issue** with patch | 太小不值得 PR 流程 |
| **无 fork** + 修复已验证 | **Issue** with inline diff/patch | 在 Issue body 中贴 diff，让维护者自己合入 |
| 发现 bug 但修复在第三方库 | **Issue** on upstream | 无法直接提 PR |
| 改动太 hacky / 仅适用特定环境 | **不做** | 留在自己的实验记录里即可 |
| 改动跨多个 repo | **拆分** | 每个 repo 独立评估 |

判断完成后，向用户报告结论和理由，等待确认后进入 Step 2。

## Step 2: 收集素材

从实验记录提取：
- **修复列表**：每个 fix 的根因、改动文件、commit hash
- **验证结果**：复现命令的输出、性能数据
- **环境信息**：能让维护者判断「这个修复在什么条件下被验证过」的最小集合

检查 fork 状态：
```bash
git -C <local_fork_path> log --oneline origin/<branch> -5
git -C <local_fork_path> remote -v
```

## Step 3: 生成 body — 等待用户审查

**先读目标 repo 的 `.github/PULL_REQUEST_TEMPLATE.md` 与 `CONTRIBUTING.md`，有就用它们的。**
下面是没有模板时的默认骨架。判据只有一条：**reviewer 两分钟内能看懂全部改动。**

### PR body

```markdown
## Summary

<one sentence: what this change makes possible that was not possible before>

### Changes
- <one line per fix, each naming the root cause>

### Tested on
- <每一项都是「改变了验证结论」的环境维度；无关的不写>

### Results
<key metrics: timing, output verification>

### Notes
- <backward compatibility: 明确说明既有用户不受影响，以及靠什么机制保证>
- <any caveats>
```

### Issue body

```markdown
## Problem

<one paragraph: what fails, under what conditions>

## Reproduction

\`\`\`bash
<minimal repro steps>
\`\`\`

## Root Cause

<brief analysis>

## Suggested Fix

<patch or description; omit if none>

## Environment
- <同上：只列影响复现的维度>
```

**`Tested on` / `Environment` 只列会改变结论的维度。** 补丁与硬件无关时列 runtime 版本就够，
堆一串无关的版本号是噪声。ROCm 移植类的典型填法：

```markdown
### Tested on
- GPU: AMD Instinct <脱敏后型号>     # 脱敏表见 external-output-boundary
- ROCm: <version>
- PyTorch: <version>
- Docker: `<image tag>`

### Notes
- All changes are backward-compatible with CUDA（`try/except` fallback，不改默认路径）
```

### 输出方式

生成完整 markdown body 后：
1. 输出 PR/Issue **title** 和 **body**
2. 给出创建链接：`https://github.com/<upstream-owner>/<repo>/compare/<base>...<you>:<branch>`
3. 用户复制到浏览器创建

## 多 repo 拆分

当改动跨多个 repo 时：

1. 按 repo 分别生成 PR/Issue body
2. body 中互相引用（`Related: <owner>/<repo>#<num>`）
3. 先提依赖库的，再提主项目的
4. 如果依赖库 PR 未合入，主项目 body 中说明 workaround

## 与其他 Skill 的协作

- **external-output-boundary**（rule）：披露 / 脱敏 / 去私料，提交前必过
- **experiment-design**：PR/Issue 素材来源
- **split-to-prs** / **autopilot**（Cursor 内置）：大改动拆成小 PR；PR 建好后跟进 review 与 CI
