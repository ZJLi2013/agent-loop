# Skills Index

This directory stores project-level Cursor skills. Keep the directory layout flat:

```text
.cursor/skills/
  <skill-name>/SKILL.md
```

Use this index to decide which skills should auto-trigger and which should be invoked explicitly.

## Auto-Trigger Workflow Skills

These are common workflow/orchestration skills. They should remain discoverable because they apply across many tasks.

- `long-running-agent-harness`: Multi-session orchestration, progress tracking, verification gates, handoff.
- `experiment-driven-doc`: Hypothesis-driven experiment records and iterative test/analyze loops.
- `agent-heartbeat`: User-visible progress updates for long-running commands.

## Conditional Execution Skills

These are operational skills with narrow trigger phrases. Keep descriptions specific so they only load for relevant remote/GPU workflows.

- `remote-ssh-github-auto`: SSH and GitHub auth repair on remote machines.
- `tmux-remote-detach`: Keep remote long jobs alive after local disconnects.
- `local-push-remote-pull-test`: Local commit/push followed by remote pull/test.
- `gpu-cluster-resource-manager`: Probe GPU nodes, choose nodes, manage cached data/models.
- `cursor-overnight-task-manager`: Batch overnight repo testing on remote GPU nodes.

## Manual / Cold Skills

These should usually include `disable-model-invocation: true` and be invoked by name. They are valuable, but too domain-specific or sensitive to load opportunistically.

- `nv-physical-ai-tracker`: NVIDIA Physical AI / robotics research tracker.
- `upstream-contribute`: Generate upstream PR/Issue drafts after an experiment is complete.

## Maintenance Rules

- Keep each `SKILL.md` concise. Move long runbooks to `reference.md` and reusable commands to `scripts/`.
- Prefer precise descriptions with explicit trigger phrases.
- Add `disable-model-invocation: true` for domain trackers, one-off research workflows, and sensitive external publishing workflows.
- Avoid nesting skills by domain; use this index for classification instead.
