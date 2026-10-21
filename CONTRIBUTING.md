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

For packaging or release changes, also run the isolated installation smoke:

```shell
python -m pip install build virtualenv
python scripts/smoke-install.py
```

See [the release guide](docs/releasing.md) for full validation, host checks, and publication steps.

The Windows installer can be smoke-tested in an isolated profile:

```powershell
$env:USERPROFILE = Join-Path $env:TEMP "agent-loop-smoke"
New-Item -ItemType Directory -Force "$env:USERPROFILE\.cursor" | Out-Null
powershell -ExecutionPolicy Bypass -File scripts/sync-to-cursor.ps1
powershell -ExecutionPolicy Bypass -File scripts/uninstall-from-cursor.ps1
```

Do not commit `.harness/`, `.agent-loop/task.md`, `.agent-loop/progress.md`, `.agent-loop/archive/`,
`.agent-loop/memory/`, hook logs, transcripts, credentials, hostnames, or private performance data.

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

## Reporting problems

Agents file only part of agent-loop's defects themselves, and no `from-agent` issue does not mean no defect.
The `self-report` skill starts from a visible signal: a Harness command errors or refuses a legitimate step, two
agent-loop rules give opposite instructions, or a human correction traces back to agent-loop wording. Issues it
files carry the `from-agent` label.

It does not catch:

- rules followed as written that produce plausible but poor results, such as scripts piling up, records that keep
  growing, or review rounds that cost more than the experiment. Each step looks compliant, and the agent has nothing
  to compare it against;
- defects the agent worked around to finish its task instead of stopping on them;
- defects that need a private project to reproduce. Reports are built only from public agent-loop material; the
  rest stay as drafts in the project's `.agent-loop/reports/`.

Open an issue yourself when:

- a result looks wrong even though no command failed: too many files, a plan that keeps growing, a review loop, a
  task that passed but missed its point;
- you corrected an agent and the correction would apply in other projects. Your statement of what you expected is
  the evidence the agent lacks;
- a project's `.agent-loop/reports/` holds a draft;
- the problem shows only in a private project. Describe it with a synthetic reproduction.

## Reporting security issues

Do not open a public Issue for vulnerabilities. Follow [`SECURITY.md`](SECURITY.md).

