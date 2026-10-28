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

A rule, skill, or reviewer-prompt change that changes a decision is accepted by behavior, not by its wording. It
changes a decision when, for some input, an agent would run, refuse, or stop a different action, keep evidence for a
different time, or hand work to a different owner. The pull request states that decision as a contract ("given X,
the agent does / refuses / stops Y"). It then replays a few public synthetic scenarios through the real call path,
once on the base branch and once with the change: the agent or reviewer reads the rules and acts, rather than a
check that the prompt contains the new sentence. One more scenario is a control the new rule must not trigger. The pull
request records the model, the inputs, and the expected and observed action of each run. A small manual or
fixed-model replay is enough. A wording change that changes no decision needs no replay.

Tests in `tests/` pin contracts: lifecycle transitions and guards, the invariants a design's module contract
names, and formats other tools read. A test that only proves one fix (a bug no contract names, output layout,
parsing details, prompt wording) lives in the pull request's history: it fails on the first commit, passes with
the fix, and is removed before merge, as the auto-fix flow does. Variants of one contract are cases of one test
with `subTest`. A compatibility test is removed with the release that ends its window.

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

Only Kernel and Adapter bugs carry the `auto-fix` label; proposals and Policy wording need a human decision, and a
Policy change that changes a decision is proven by the behavior replay described under Pull requests, not by a
failing test. Issues labelled `auto-fix` are not fixed on their own. The maintainer runs `.github/auto-fix/run.ps1` on demand, which
hands one issue to a sandboxed Codex agent and marks its pull request ready only after CI fails on the agent's
regression test alone and passes with the fix. It then reverts the test, so the suite does not grow with every fix;
the test stays in the pull request's history. The script does not read why the first commit failed: a test that
crashes or an unrelated failure also turns it red. Before merging, the maintainer checks that the first commit's
failing job is the new test's assertion and reviews the fix itself. An issue the agent cannot reproduce from a public
checkout gets a comment and stays open for a human.

## Reporting security issues

Do not open a public Issue for vulnerabilities. Follow [`SECURITY.md`](SECURITY.md).

