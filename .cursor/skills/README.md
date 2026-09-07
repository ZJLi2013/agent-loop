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
- `experiment-driven-doc`: Hypothesis, gates, experiment records, writing voice.
- `long-running-agent-harness`: Multi-session runbook, progress, verification, handoff.
- `agent-heartbeat`: User-visible progress for commands expected to run longer than 60s.

## Manual / Cold Skills

These include `disable-model-invocation: true` and are invoked by name.

- `code-to-kernel-diagram`: `nn.Module` forward → per-kernel dataflow.
- `cross-agent-contract`: Two agents/repos align via a shared markdown contract.
- `cursor-overnight-task-manager`: Batch overnight repo testing on remote GPUs.
- `gpu-cluster-resource-manager`: Probe nodes, pick a host, manage cached data/models.
- `local-push-remote-pull-test`: Local push then remote pull/test.
- `nv-physical-ai-tracker`: NVIDIA Physical AI / robotics research tracker.
- `remote-ssh-github-auto`: SSH login and remote GitHub auth repair.
- `research-to-blog`: Paper/survey → public blog / 公众号.
- `tmux-remote-detach`: Keep remote jobs alive after local disconnect.
- `upstream-contribute`: Upstream PR/Issue drafts after an experiment.
- `video-frame-analysis`: ffmpeg extract frames and inspect video evidence.

## Maintenance Rules

- **Writing/updating a `SKILL.md`: follow `.cursor/rules/skill-authoring.mdc`** (auto-attaches on `SKILL.md`). It owns the size budget and anti-bloat constraints; don't restate them here.
- Keep each `SKILL.md` concise. Move long runbooks to `reference.md` and reusable commands to `scripts/`.
- Prefer precise descriptions with explicit trigger phrases.
- Auto-trigger only the four skills above. Everything else gets `disable-model-invocation: true`.
- Avoid nesting skills by domain; use this index for classification instead.
