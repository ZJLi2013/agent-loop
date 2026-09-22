# Contributing

Thanks for improving agent-loop. Start with [`design.md`](design.md): the repository separates a stable
state-machine kernel, state-specific policies, and platform adapters.
Participation is governed by [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md).

## Before coding

Open an Issue first when a change:

- adds or changes a lifecycle state, event, transition, or non-bypassable guard;
- changes a persisted schema or public CLI;
- changes global platform hook behavior;
- removes or renames a rule or skill.

Classify the proposal:

1. project-specific difference → config/profile;
2. behavior within an existing state → the owning policy/skill;
3. platform integration → adapter/hook;
4. new lifecycle state/event/guard → Kernel.

Explain why the existing owner cannot absorb the change. Kernel changes should include a reviewed Plan Revision
and transition tests.

## Development

Requirements: Python 3.11+ and git.

```shell
python -m unittest discover -s tests -v
git diff --check
```

The Windows installer can be smoke-tested in an isolated profile:

```powershell
$env:USERPROFILE = Join-Path $env:TEMP "agent-loop-smoke"
New-Item -ItemType Directory -Force "$env:USERPROFILE\.cursor" | Out-Null
powershell -ExecutionPolicy Bypass -File scripts/sync-to-cursor.ps1
powershell -ExecutionPolicy Bypass -File scripts/uninstall-from-cursor.ps1
```

Do not commit `.harness/`, `.agent-loop/task.md`, `.agent-loop/progress.md`, `.agent-loop/memory/`, hook logs, transcripts,
credentials, hostnames, or private performance data.

## Pull requests

A pull request should contain:

- the problem and the chosen layer (config / Policy / Adapter / Kernel);
- evidence: tests, exit codes, or reproducible output;
- compatibility and migration notes for schema, CLI, hook, rule, or skill changes;
- documentation updates in the single owning location;
- the AI disclosure required by [`AI_POLICY.md`](AI_POLICY.md).

New behavior must remove the path it replaces. Do not duplicate a transition in prose, create a second backlog,
or add text-matching tests where an executable transition/guard test is possible.

Commit subjects are imperative statements of the resulting state. Keep unrelated changes in separate commits.

## Reporting security issues

Do not open a public Issue for vulnerabilities. Follow [`SECURITY.md`](SECURITY.md).

