# Episodes

## experiments
- [2026-09-20] skill 16 → 10，按「一个知识点一个归属」重分；净减 600 行而能力未减，说明减掉的确实是重复
- [2026-09-20] 调度器从 skill 改成常驻 rule（`agent-loop`）。机制原因：rule 每轮在上下文，skill 要先被 description 匹配命中
- [2026-09-20] memory 的 GATE 做成 `postToolUse` hook 而非规则。实测拦住了「重跑已被推翻的 noise aug 实验」
- [2026-09-21] 注入通道确认可用：`additional_context` 以 `<system_reminder>` 出现在 Read 结果尾部。
  判据用的是 hook 运行时生成、别处不落盘的 nonce——只有真进了上下文才复述得出来

## disproved
- [2026-09-20] 「把 P0–P4 放进全局 skill 就能影响 PR review」→ **不成立**。Bugbot 只读 `.cursor/BUGBOT.md` 与 dashboard 规则，不读 skills，也不读 `.cursor/rules/*.mdc`。要在 PR 阶段生效只能写那两处
- [2026-09-20] 「skill 设成 auto-trigger 就会被用上」→ **不成立**。旧的编排 skill 一直是 auto，仍需反复提醒；语义匹配是概率性的，调度器不能依赖它
- [2026-09-20] 「事实丢失发生在会话边界」→ **不成立**。开一天不关的窗口才是主场景，它没有「开工」时刻，上下文压缩是静默的
- [2026-09-21] 「memory hook 已经在注入」→ **不成立**。它从上线起就从未在真实事件里注入过：
  Cursor 在 Windows 上往 stdin 写 UTF-8 **带 BOM**，`json.loads` 抛 `JSONDecodeError`，脚本走兜底返回 `{}`。
  当初的验收是手动 `echo | python` 喂干净 JSON——那条路径绕开了 BOM。修法：
  `sys.stdin.buffer.read().decode("utf-8-sig")`

## rejected
- [2026-09-20] 不用硬链接链 rules：`git pull` / `checkout` 是删掉重写，一拉就断且**不报错**，副本看着正常但永不更新
- [2026-09-20] memory 不嵌在 `task.md` 顶部：生命周期不同，且挡住了后续扩展
- [2026-09-20] `INDEX.md` 不索引 skills：name + description 每轮已在上下文，重复付费，且硬路径会随改名漂移（一天内改名三次）
- [2026-09-20] code 相关的四个 skill/rule 不合并：它们在不同时刻加载，合并会导致写代码时载入 review 清单
- [2026-09-20] `experiment-design` 不再为压到 150 行而砍：剩下的是两道门与 Workflow，属于删能力不是去重
