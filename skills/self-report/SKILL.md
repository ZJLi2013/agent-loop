---
name: self-report
description: >-
  运行中遇到 agent-loop 自身的缺陷时，归因、去重、检查后发到 ZJLi2013/agent-loop 的 issue；
  过不了归因或检查的留在项目里。触发：Harness 命令报错或 guard 拒绝合法的一步、两条 agent-loop 规则指令相反、
  human 纠偏追到 agent-loop 的规则或 skill 措辞。
  Use when a Harness command errors or refuses, two agent-loop rules conflict, or a correction traces to agent-loop wording.
---

# Self Report

**边界**：项目自身的失败归 `when-to-stop` 与 `agent-memory` 的 lessons；他人仓库的 PR / Issue 归 `upstream-contribute`；
披露、脱敏、去私料的规则归 `external-output-boundary`，本 skill 只做发布前的机器检查。

上报不改变当前 task 的状态与失败计数；发布或存稿后回到原来的 task。

## 1. 归因

三样都写得出才上报，否则记进项目 `lessons`：

- agent-loop 的文件与行，以及已安装 checkout 的 commit（`git -C <checkout> rev-parse --short HEAD`；Cursor 安装时
  checkout 是 `~/.cursor/harness` junction 指向的仓库）；
- 期望与实际；
- 自带的最小复现：Harness / adapter 缺陷给在 agent-loop 公开 checkout 上可重建的命令，以及合成的 `state.json` /
  `task.md` 片段；Policy 缺陷引原句与它导致的动作。

## 2. 内容来源

标题、正文、评论只由三类材料组成：agent-loop 仓库里的代码与规则原文、可在公开 checkout 上重建的合成复现、
对期望与实际行为的自述。项目里的任何原文（日志、文档、代码、transcript、数据、指标）都不进正文；
离开它说不清的报告只存草稿。检查脚本无命中不代表满足这一条。

## 3. 去重

```bash
gh issue list --repo ZJLi2013/agent-loop --state all --search "<关键词>"
```

同一缺陷已有 open issue：评论追加新证据。已 closed、而缺陷在修复之后的 commit 上复现：新开并链接旧的。

## 4. 起草

- bug 按 `.github/ISSUE_TEMPLATE/bug.yml` 的字段写成 `###` 小节（Commit or release、Layer、Reproduction、
  Expected boundary、Actual result and evidence），提案按 `feature.yml`。
- 标题 `[bug] …` / `[proposal] …`，陈述缺陷本身。
- 末尾一行 `AI use:`，写工具、模型，以及发布前无人审阅。语态归 `write-for-humans`。

## 5. 检查与发布

正文写进文件，标题单独传给本 skill 目录下的检查脚本：

```bash
python <本 skill 目录>/check_report.py --title "<标题>" body.md
```

退出码 0，且全仓今天的 `from-agent` issue 少于 5 条时发布：

```bash
gh issue list --repo ZJLi2013/agent-loop --label from-agent --state all --search "created:>=<YYYY-MM-DD>" --json number
gh issue create --repo ZJLi2013/agent-loop --title "<标题>" --body-file body.md \
  --label from-agent --label auto-fix --label <bug|proposal> --label <kernel|policy|adapter>
```

评论同样先过检查，再 `gh issue comment <N> --repo ZJLi2013/agent-loop --body-file comment.md`。
正文一律用 `--body-file`：PowerShell 把多行字符串作参数传给 `gh` 时会丢掉换行。

检查未通过、超过当日上限或 `gh` 失败时，存为项目内 `.agent-loop/reports/<YYYY-MM-DD>-<slug>.md`
（首行标题，其后正文，末尾附未通过的检查输出），并告诉 human。
