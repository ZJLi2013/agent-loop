---
name: upstream-contribute
description: >-
  判断一个修复该提 PR、提 Issue 还是不提，并生成 body 草稿。目标 repo 有 PR 模板就用它的，
  有 review skill 就先在 draft PR 上自审再 ready；ready 之后的跟进只起草，push 与回复等用户确认。
  Use when contributing a fix back to someone else's repo, or following up on an upstream PR.
disable-model-invocation: true
---

# Upstream Contribute — 本地修复 → GitHub PR / Issue

评估在他人仓库里做出的修复值不值得提，并生成草稿。提交流程**不依赖 gh CLI**，生成 markdown body 供用户在浏览器中创建；
ready 之后的跟进（Step 5）要用 `gh` 读 PR 状态。

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
上游的 agent skill 目录（`.agents/skills/`、`.claude/skills/`、`.github/skills/`，或 `AGENTS.md` /
`CONTRIBUTING.md` 点名的位置）里有写 PR 的 skill 时，按它写 body、跑它带的检查。
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
3. 用户复制到浏览器创建；上游有 review skill 时选 **Create draft pull request**，进入 Step 4

## Step 4: 上游有 review skill 时 — draft → 自审 → ready

**维护者会用上游自己的 review skill 审 PR，就先在 draft 上跑一遍**，让它的清单在 ready 之前命中，
而不是每条 finding 都花掉维护者一轮往返。

1. 在 Step 3 的同一批目录里找 review skill。读上游默认分支上的版本（`git show origin/<default>:<path>`），
   本地 checkout 可能落后或带着别人没有的 skill。没有 review skill 就跳过本步，流程不变。
2. 按它要求的输入运行：要 PR URL 的对 draft PR 跑；接受本地 diff 的可以在建 draft 之前跑。
3. 每条 finding 先验证再处置。成立的在 fork 分支上修并推到 draft；不成立的写进 PR body（模板有备注节就放那里，
   没有就加 `Design notes` 小节），每条附证据：代码位置、被破坏的约束或链接。维护者的 review 多半报出同样的误判，
   body 里已有回答就省掉一轮。
4. 修完重跑一次，没有新的成立项时告诉用户可以 mark ready。

建 draft 与建 PR 一样是对外动作：先等用户确认，`external-output-boundary` 对 draft 同样适用。

## Step 5: ready 之后 — 跟进冲突、review 与 CI

**发现、判断、修复与验证可以全自动；push 到 PR 分支、发评论、resolve thread 先给用户过目。** 回复以用户的名义发出，
`external-output-boundary` 的审阅要求对评论同样成立；目标项目的 AI 政策明确允许 agent 直接回复时从它。

1. 找要跟进的 PR：`gh search prs --author=@me --state=open -- -user:<you>` 列出上游 open PR，逐个读
   `gh pr view <url> --json mergeable,statusCheckRollup,reviews,comments` 与行内评论
   （`gh api repos/<owner>/<repo>/pulls/<n>/comments`）。有冲突、required check 失败，或最后一条评论 / review /
   行内评论不是用户的，才要跟进。
2. 按冲突 → 未解决评论 → CI 的顺序处置。评论按 Step 4 第 3 条判断：成立的修，不成立的起草附证据的回复；
   涉及安全、许可、超出 PR 范围或要用户拿主意的标「问人」。CI 只修本 PR 改动引起的失败。
3. 修复提交到 fork 上不挂 PR 的 `followup/<branch>`（从 PR 分支的远端最新状态拉出），跑能证明修复的最窄检查。
   PR 分支不动，维护者看不到未经用户确认的改动。
4. 每个 PR 交一段报告：链接、每条 finding 的处置与回复草稿、`followup/<branch>` 的 commit 与检查结果、
   用户确认后要执行的命令（把 PR 分支快进到 `followup/<branch>`、发出回复）。

## 多 repo 拆分

当改动跨多个 repo 时：

1. 按 repo 分别生成 PR/Issue body
2. body 中互相引用（`Related: <owner>/<repo>#<num>`）
3. 先提依赖库的，再提主项目的
4. 如果依赖库 PR 未合入，主项目 body 中说明 workaround

## 与其他 Skill 的协作

- **external-output-boundary**（rule）：披露 / 脱敏 / 去私料，提交前必过
- **experiment-design**：PR/Issue 素材来源
- **split-to-prs**（Cursor 内置）：大改动拆成小 PR。上游 PR 的跟进走 Step 5，不用 `autopilot`：它会自己回复并 resolve thread
