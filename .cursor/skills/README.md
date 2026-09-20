# Skills Index

This directory stores project-level Cursor skills. Keep the directory layout flat:

```text
.cursor/skills/
  <skill-name>/SKILL.md
```

Use this index to decide which skills should auto-trigger and which should be invoked explicitly.

## Auto-Trigger

Daily path plus long-running orchestration. Descriptions stay in context; bodies load when the task matches.

- `feature-dev-pipeline`: Backlog → Goal → design → build+experiment → backfill.
- `experiment-driven-doc`: The two gates (decision value, acceptance ladder) and the experiment record template.
- `long-running-agent-harness`: Multi-session runbook, progress, verification, handoff.
- `agent-heartbeat`: User-visible progress for commands expected to run longer than 60s.

## Manual / Cold Skills

These include `disable-model-invocation: true` and are invoked by name.

- `remote-exec`: Get work onto a remote GPU node, keep it alive, auto-repair failures, manage storage.
- `code-review`: PR/diff review with sglang-diffusion-routing P0-P4 + four-section template.
- `code-to-kernel-diagram`: `nn.Module` forward → per-kernel dataflow.
- `upstream-contribute`: PR-vs-Issue judgement and body templates for upstream contributions.
- `research-to-blog`: Paper/survey → public blog / 公众号.

## Ownership: one knowledge point, one home

The failure mode this library keeps hitting is the same judgement written in three places, then
only one of them getting updated. Before adding a section, find its owner below and link instead.

| 知识点 | 唯一归属 |
|---|---|
| 主线、解释性膨胀、标题写问题本身、清单不写段落、肯定式陈述、陈述当前为真 | `narrative-spine` (rule) |
| 对话专属：第一句即结论、只答被问到的对象、说「做不到」前先查 | `reply-conclusion-first` (rule) |
| 什么先自修、什么才停下来问人、预算、硬性中止 | `experiment-budget-gate` (rule) |
| AI 披露、GPU 型号脱敏、对外去私料 | `external-output-boundary` (rule) |
| SKILL.md 体量与反膨胀 | `skill-authoring` (rule, globs on `SKILL.md`) |
| 注释密度与 WHY-only | `code-comments` (rule) |
| 决策价值门判别法、验收判据阶梯、Phase 0、exp 文档章节模板 | `experiment-driven-doc` |
| backlog 排序、Goal-first、四阶段循环、持续模式 | `feature-dev-pipeline` |
| 跨会话状态、runbook、handoff | `long-running-agent-harness` |
| SSH / 选节点 / detach / 存储 / 远端失败自修表 | `remote-exec` |

**任务状态只有一个真相源**：走 `feature-dev-pipeline` 时是它的 backlog 文档，harness 不再建
`tasks.json`；没有 backlog 的长任务才用 `tasks.json`。

## Maintenance Rules

- **Writing/updating a `SKILL.md`: follow `.cursor/rules/skill-authoring.mdc`** (auto-attaches on `SKILL.md`). It owns the size budget and anti-bloat constraints; don't restate them here.
- Keep each `SKILL.md` concise. Move long runbooks to `reference.md` and reusable commands to `scripts/`.
- Prefer precise descriptions with explicit trigger phrases.
- Auto-trigger only the four skills above. Everything else gets `disable-model-invocation: true`.
- A skill that is one concrete application rather than a reusable workflow belongs in a
  `reference.md` section of the workflow it applies, not as its own top-level skill.
- Avoid nesting skills by domain; use this index for classification instead.
