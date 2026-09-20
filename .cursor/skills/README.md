# Skills Index

This directory stores project-level Cursor skills. Keep the directory layout flat:

```text
.cursor/skills/
  <skill-name>/SKILL.md
```

Use this index to decide which skills should auto-trigger and which should be invoked explicitly.

## The loop

`agent-loop` (an always-applied **rule**, not a skill) is the scheduler: every turn it locates
which cell of the loop the work is in and names the skill to read. It has to be a rule — a
scheduler that must first be matched by description is not a scheduler, which is why the previous
orchestration *skill* kept failing to fire.

```text
Goal ─► PLAN ─► SELECT ─► DESIGN ─► EXECUTE ─► EVALUATE ─┬─ pass ─► CLOSE ─┐
         │        │          │          │                │                │
         │        │          │          │                └─ fail ─► DIAGNOSE
  feature-     task-state  experiment-  │                            │
   planning                design       │              按类别自修，用尽才问人
         │                              │                            │
         └──────────────── 下一个 task ◄─┴────────────────────────────┘
                                  │
                         全部通过 ─► DONE（报告并停）

         .cursor/memory/facts.md  ← 要用一个具体值就读它，第二次用到就写回
              （横穿每一格，不是其中一格）
```

`agent-memory` is not a cell. **The file is the source of truth and the conversation is a cache**:
read a value out of `facts.md` when you are about to put it in a command, rather than recalling it.
That sidesteps having to notice that context was compacted — in a window left open all day there is
no "session start" to hang a re-read on, and dropped facts are silent. `agent-heartbeat` likewise
crosses the loop: it hangs off any command expected to exceed 60 seconds.

Everything in the loop triggers on a mechanically checkable condition. `remote-exec`,
`code-review`, `upstream-contribute`, `research-to-blog` and `code-to-kernel-diagram` all sit
**outside** it and run only when the user asks. Clearing `task.md` means DONE, not "now open a PR".

**Drift control is an invariant, not a reminder.** Exactly one `task.md` row is `🔬 doing`, and a
change belongs to it only if it moves that row's acceptance checkpoint from failing to passing.
Anything else becomes its own row before the work starts; the count of `🚧 blocked` rows is the
nesting depth, and two is the limit. A self-check phrased as "am I drifting?" would never fire —
every step of a drift looks justified — so the test is anchored on a criterion already written down.

## Auto-Trigger

Descriptions stay in context; bodies load when the task matches.

- `feature-planning`: Large feature → prioritized task.md rows + per-subtask design doc.
- `task-state`: task.md schema, acceptance checkpoints, failure counter, cross-session handoff.
- `agent-memory`: `.cursor/memory/` — concrete values that must survive across sessions.
- `experiment-design`: The two gates (decision value, acceptance ladder) and the record template.
- `agent-heartbeat`: User-visible progress for commands expected to run longer than 60s.

## Manual / Cold Skills

These include `disable-model-invocation: true` and are invoked by name.

- `remote-exec`: Get work onto a remote GPU node, keep it alive, auto-repair failures, manage storage.
- `code-review`: Four-section review output; the standard comes from the target repo, not this skill.
- `code-to-kernel-diagram`: `nn.Module` forward → per-kernel dataflow.
- `upstream-contribute`: PR-vs-Issue judgement and body templates for upstream contributions.
- `research-to-blog`: Paper/survey → public blog / 公众号.

## The code path, by who executes it

These pieces deliberately stay separate: they fire at different moments, and two of them run
outside this library entirely. Merging them would load a review checklist while writing code.

| 阶段 | 谁执行 | 只有这个生效 |
|---|---|---|
| write | 会话内 agent | `code-hygiene` rule |
| commit | 会话内 agent | `code-hygiene` rule（实验编号见 `experiment-design`） |
| review 本地 diff | 会话内 agent / `review-bugbot`、`review-security` subagent | `code-review` |
| **review PR** | **Cursor 云端 Bugbot** | **`.cursor/BUGBOT.md` + dashboard Team / Repository Rules** |
| PR body | 会话内 agent | `upstream-contribute` |
| 跨仓库边界 | 会话内 agent | `external-output-boundary` rule |

**Bugbot 不读 `.cursor/rules/*.mdc`，也不读 Skills。** 想让某条标准影响 PR 上真正跑的那次
review，只能写进被审 repo 的 `.cursor/BUGBOT.md`，或配一次 dashboard 的 Team Rules。

## Ownership: one knowledge point, one home

The failure mode this library keeps hitting is the same judgement written in three places, then
only one of them getting updated. Before adding a section, find its owner below and link instead.

| 知识点 | 唯一归属 |
|---|---|
| 循环的状态机、路由到哪个 skill、失败按类别分流 | `agent-loop` (rule) |
| 结论先行、主线、解释性膨胀、只答被问对象、陈述真值、说「做不到」前先查 | `write-for-humans` (rule) |
| 什么先自修、什么才停下来问人、预算、硬性中止 | `when-to-stop` (rule) |
| AI 披露、GPU 型号脱敏、对外去私料 | `external-output-boundary` (rule) |
| SKILL.md / rule 的准入体量，以及「该放 rule / skill / hook」 | `authoring` (rule, glob) |
| 多行命令先写文件；PowerShell 的坑 | `shell-exec` (rule) |
| 注释密度、WHY-only、commit message | `code-hygiene` (rule) |
| review 的四段输出、严重度轴、vibe-coding 识别 | `code-review` |
| 决策价值门判别法、验收判据阶梯、Phase 0、exp 文档章节模板 | `experiment-design` |
| 大 feature 拆子任务、Goal-first、四阶段、设计文档 | `feature-planning` |
| `task.md` schema、验收检查点、失败计数、跨会话交接 | `task-state` |
| 跨会话要保住的具体值：准入判据、覆盖语义、过期验证 | `agent-memory` |
| SSH / 选节点 / detach / 存储 / 远端失败自修表 | `remote-exec` |

**任务状态只有一个真相源：`task.md`。** 不建 `tasks.json`，不维护第二份 backlog。

## Maintenance Rules

- **Writing/updating a `SKILL.md`: follow `.cursor/rules/authoring.mdc`** (auto-attaches on `SKILL.md`). It owns the size budget and anti-bloat constraints; don't restate them here.
- Keep each `SKILL.md` concise. Move long runbooks to `reference.md` and reusable commands to `scripts/`.
- Prefer precise descriptions with explicit trigger phrases.
- Auto-trigger only the four skills above. Everything else gets `disable-model-invocation: true`.
- A skill that is one concrete application rather than a reusable workflow belongs in a
  `reference.md` section of the workflow it applies, not as its own top-level skill.
- Avoid nesting skills by domain; use this index for classification instead.
