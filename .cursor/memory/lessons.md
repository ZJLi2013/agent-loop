# Lessons

<!-- 上限 15 条。[x1] 记一次 / [x2] 又犯 / [x3] 晋升为 .cursor/rules 并从这里删掉。 -->

## windows
- [x3] [2026-09-20] PowerShell 无 heredoc、`.ps1` 需 UTF-8 BOM、`Remove-Item` 删不了 junction
  → 已晋升为 `.cursor/rules/shell-exec.mdc`，本条保留作为晋升记录，下次清理时删
- [x1] [2026-09-20] `>` 重定向写出 UTF-16LE，下游按 UTF-8 读会在 `0xff` 处报错；要 UTF-8 用 `Set-Content -Encoding utf8`
- [x1] [2026-09-20] 跨行拆写的名字（ASCII 图里的 `feature-` + `-pipeline`）逃得过全局替换，改名后要单独查一遍图
- [x1] [2026-09-21] hook 的 stdin 是 UTF-8 **带 BOM**，`sys.stdin.read()` + `json.loads` 必炸。
  统一用 `sys.stdin.buffer.read().decode("utf-8-sig", errors="replace")`
- [x1] [2026-09-21] 仓库改名/移动会让 `~/.cursor` 下的 junction 全部指向不存在的路径，且**不报错**：
  junction 目录本身 `Test-Path` 仍为 True，hook 照常执行、exit code 0、只是「produced no output」。
  改名后必须重跑 `sync-to-cursor.ps1`。验的是 junction 下的**文件**在不在，不是目录在不在

## authoring
- [x1] [2026-09-20] 判断一条规则该放哪层，看它**需要在什么时刻生效**：写代码时→rule，审代码时→skill，PR 时→BUGBOT.md，必须强制→hook
- [x1] [2026-09-20] 写成「自查有没有漂 / 要不要查记忆」的规则不会触发——自省时刻不会到来。判据要锚在已写下的东西上（检查点、正在执行的命令）
- [x2] [2026-09-20] 尾部的 Key Principles / 原则小节，八成在复述本文正文。加之前先问它有没有新增决策
- [x1] [2026-09-21] hook / 集成类的验收必须走**真实事件**。手动 `echo json | python script.py` 只测了脚本逻辑，
  绕开了调用方的 stdin 编码、cwd、相对路径——三处都出过静默失效
- [x1] [2026-09-20] 解释「这条规则为什么这么设计」的句子一律删；保留「关于世界的因果」（如"放宽重试上限会让坏环境烧一整夜"）
