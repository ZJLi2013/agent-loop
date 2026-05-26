---
name: long-running-agent-harness
description: Orchestrates long-running coding, research, and experiment tasks with an initializer phase, incremental agent loop, verification gates, and durable handoff artifacts. Use when work may span multiple context windows, remote runs, batch experiments, broad refactors, unattended runs, or when the user mentions init agent, harness, sub-agents, long-running task, progress tracking, or handoff.
---

# Long-Running Agent Harness

Use this skill for multi-session work where an agent might otherwise lose context, overreach, or declare completion too early.

This skill is the **orchestration layer**. It does not replace domain-specific skills:

- Use `experiment-driven-doc` for hypothesis, experiment design, results, and conclusions.
- Use `agent-heartbeat` for user-visible progress during commands expected to run longer than 60 seconds.
- Use `tmux-remote-detach` when a remote job must survive local disconnects.
- Use project-specific skills or docs for domain details.

## Core Principle

Separate long work into:

1. **Initializer phase**: define scope, artifacts, run commands, and completion criteria.
2. **Incremental work phase**: complete one small task at a time.
3. **Verification phase**: prove the change or experiment outcome before marking it done.
4. **Handoff phase**: leave durable notes for the next agent/session.

Do not rely on chat history alone. Durable state must live in the repo or an agreed project artifact.

## Harness Artifacts

For a new long-running task, create or update these files:

- `.cursor/harness/progress.md`: chronological progress log, current state, blockers, next action.
- `.cursor/harness/tasks.json`: structured task list with stable IDs and pass/fail status.
- `.cursor/harness/runbook.md`: exact commands for setup, smoke tests, batch runs, sync, and cleanup.

If the repo already has an accepted experiment log, roadmap, or issue tracker, keep stable conclusions there. Use `.cursor/harness/progress.md` for active working notes and handoff state.

## Initializer Phase

When starting a long-running task:

1. Read recent repo context: README, relevant docs, relevant scripts, and recent git history.
2. Define the smallest useful task breakdown in `.cursor/harness/tasks.json`.
3. Write `.cursor/harness/runbook.md` with commands that a fresh agent can run without rediscovery.
4. Write `.cursor/harness/progress.md` with:
   - goal
   - current assumptions
   - known risks
   - first task to execute
   - verification method
5. If the task includes remote work, unattended tests, or long batch jobs, include heartbeat/status expectations and log paths.

Prefer JSON for task status because it is harder to casually rewrite than markdown checklists.

## Task Schema

Use this shape for `.cursor/harness/tasks.json`:

```json
[
  {
    "id": "short-stable-id",
    "category": "coding|docs|experiment|infra|verification",
    "description": "One observable outcome.",
    "steps": ["Concrete step 1", "Concrete step 2"],
    "verification": "Command, artifact, or observation required before pass.",
    "passes": false,
    "notes": ""
  }
]
```

Only change `passes` to `true` after verification. Do not delete failing tasks just because they are inconvenient.

## Incremental Agent Loop

At the start of each session:

1. Read `.cursor/harness/progress.md`, `.cursor/harness/tasks.json`, and `.cursor/harness/runbook.md`.
2. Check `git status` and recent `git log`.
3. Run the smallest smoke test or environment check from the runbook if practical.
4. Select one unfinished task with high priority and narrow scope.
5. State the selected task and verification plan before editing.

During implementation:

- Keep changes scoped to the selected task.
- Prefer existing project patterns over new abstractions.
- For experiments, invoke `experiment-driven-doc` and record hypothesis, command, expected result, actual result, and conclusion in the project’s experiment record.
- Use subagents only for bounded parallel work: code exploration, log analysis, test investigation, or review.

Before ending the session:

1. Run the relevant verification command or explain why it could not run.
2. Update `tasks.json` only for tasks actually verified.
3. Append a handoff entry to `progress.md`.
4. Leave the repo in a clean, understandable state.

## Progress Entry Template

Append entries like this:

```markdown
## YYYY-MM-DD HH:MM - Short Title

Task: `task-id`
Status: done|blocked|in-progress

What changed:
- ...

Verification:
- Command/artifact:
- Result:

Next action:
- ...

Notes for next agent:
- ...
```

## Completion Criteria

A long-running task is complete only when:

- all required tasks in `tasks.json` have `passes: true`, or remaining failures are explicitly accepted;
- verification evidence is recorded in `progress.md`;
- final stable conclusions are summarized in the appropriate project doc, issue, PR, or report;
- the next agent can understand the state from durable artifacts without reading the full chat.
