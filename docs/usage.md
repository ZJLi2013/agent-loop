# Use agent-loop in a working project

[Quickstart](quickstart.md) · [中文入口](../README.md) · [English entry](../en.md)

## Install and choose a mode

Install the CLI from a repository checkout with `python -m pip install .`. For Cursor enforced mode use
`python -m pip install -e .` instead: the installer links the hooks to the checkout, and an editable install
keeps the CLI on the same code after a branch switch or pull. Keep your working project separate from the
agent-loop checkout.

| Mode | What you get |
|---|---|
| Portable | CLI commands and policies used by your host; the host controls its own lifecycle |
| Cursor enforced | Windows installation below adds memory, stop, and preCompact hooks |

For Windows + Cursor, run from the agent-loop checkout:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/sync-to-cursor.ps1
```

The installer links the checkout into `%USERPROFILE%\.cursor`, including the rules directory, individual
skills, harness, and hooks. Existing ordinary directories with the same names are moved to timestamped
backups. Review those backups if you have custom rules/hooks. Restart Cursor after installation and make
sure the Python interpreter visible to Cursor is 3.11+; activation of a venv in a terminal does not necessarily
change Cursor's environment. Keep the checkout in place and use a trusted version. See [Security](../SECURITY.md).

The automated Windows job checks installer wiring in an isolated profile. It does not launch Cursor or prove
compatibility with every Cursor release. Before publishing, also run the real-host smoke in [Releasing](releasing.md).

## Create a reviewed plan

In your working project, write a plan document describing the Goal, scope, current conclusion, next decision,
and acceptance criteria. The filename is flexible. Include:

```text
Plan Revision: 1
Plan Review: proposed
```

Create `.agent-loop/task.md` with the current proposed task bound to `r1`. The
[example task](../examples/minimal-project/task.md) shows the table format, but starts as `doing` for its
pre-approved demonstration; new project tasks should start as `📝 proposed`.

Review the plan, then set `Plan Review: approved` and activate one task as `🔬 doing`.
When a reviewer is configured, first obtain its advisory plan review as described below.

From the working project root, initialize a verifier appropriate for that project's Goal:

```sh
agent-loop-harness init --task t1 --plan-doc plan.md -- python -B -m unittest -v
```

Replace the command with the project's actual tests or experiment checks. Initialize locks the verifier
command and budget. Run work through `agent-loop-harness exec -- <command>`, then
`agent-loop-harness verify`. Other host tool calls remain outside the runner's hard-control boundary.
Defaults include a Goal Review after three runner actions, 60 minutes, or failure; refresh also occurs at
relevant host events. `init --help` lists budget and attention settings.

## Optional independent reviewer

Create `.agent-loop/reviewer.json` **before** plan review and task initialization. It declares an executable
command, with a timeout, that reads the generated `.harness/review/prompt.md` and follows its output contract.
Use a reviewer CLI/model available in your environment. The conceptual configuration is:

```json
{
  "argv": ["YOUR_REVIEWER_CLI", "YOUR_NONINTERACTIVE_ARGUMENTS"],
  "timeout_seconds": 1800
}
```

Replace both placeholders with a real argv array; this is not a runnable command. The command must run
noninteractively, read the generated prompt, and write its requested report/decision. A configuration example
for a Windows worker using an existing reviewer CLI in WSL is:

```json
{
  "argv": ["wsl.exe", "--", "bash", "-lc",
    "codex exec -s workspace-write 'Read .harness/review/prompt.md and follow it exactly.'"],
  "timeout_seconds": 1800
}
```

This example requires that CLI to be installed and authenticated in WSL, and that the project is accessible
there. Use the command supported by your installed tool/version; the harness does not bundle it. Credentials
and model choice remain the responsibility of that tool. Reviewer configuration is local runtime and should
not be committed. The generated contract and role boundaries are described in [design.md](../design.md).
When configuring review, link the project design/plan from the active task, using a path relative to
`.agent-loop/task.md` (the example task already does this).

```sh
agent-loop-harness plan-review --plan-doc plan.md
```

Read the report, approve or revise the plan, activate the task, and initialize as above. The plan reviewer
advises but cannot approve the plan. After a verified task, the configured reviewer runs automatically,
interprets the evidence, and selects `continue`, `ask_human`, or `stop`. Proposed successor tasks need explicit
activation under the applicable approval policy. A project may add `.agent-loop/review-checklist.md` for
domain-specific checks; sample inputs and actual outputs help the reviewer judge whether the work measured the Goal.

## Corrections and Goal Review

To change the Goal or scope while work is active:

```sh
agent-loop-harness pause --require-revision --reason "Goal changed"
```

Update the plan with a new revision and proposed review status, reconcile the task's revision and scope,
obtain plan review if configured, approve, then `agent-loop-harness resume`.

For a pending Goal Review, record the evidence and decision:

```sh
agent-loop-harness goal-review --decision continue --evidence "The failed test identifies a repair within the approved Goal."
```

Use `replan` or `stop` when the evidence warrants it. `continue` does not bypass a required plan revision.

## Memory and long-task observation

Copy the four Markdown templates from `skills/agent-memory/templates/` in the agent-loop checkout into
`<working-project>/.agent-loop/memory/`. Each project owns its facts, episodes, lessons, and bounded index.
The Cursor adapter injects retrieval context when the active task is read. See [Memory](../study/memory.md)
for rationale and [Policies](../skills/README.md) for owners.

Closed tasks and old handoffs move to `.agent-loop/archive/`. Runtime evidence lives in `.harness/`, with
bounded logs and artifacts. Preserve project evidence that must outlive runtime retention in project-owned
storage. Heartbeat policy observes detached jobs; see [Heartbeat](../study/heartbeat.md).

## Optional phone checkpoints

The pager is a separate package. Follow [tools/pager](../tools/pager/README.md) for Outlook/Graph or
[Feishu setup](../tools/pager/docs/feishu.md). Configure `.agent-loop/pager.json` in the working project.
Plan approval, reviewer escalation, repeated review failure, and budget exhaustion can be paged to a human.
The worker must remain running to wait for a reply; pager cannot restart an exited agent.

## Optional on-demand skills

Skills outside the loop load only when named: type `/<skill-name>` in Cursor chat followed by the request,
or name the skill in the message. The list is under *Explicit / cold policies* in [Policies](../skills/README.md).
For example, to turn a closed research Goal into an arXiv-style paper and a short teaser:

```text
/research-to-paper Write wm_forge's conclusions as an arXiv paper, then make a 10 s teaser.
```

The sync script links these skills into Cursor only. Codex does not see them; point it at
`skills/<skill-name>/SKILL.md` in the agent-loop checkout instead.

## Upgrade and uninstall

Before changing the harness version, finish or pause active work, inspect the changelog, and preserve the
working project's state and evidence. For v0.1, finish active tasks before switching versions when no explicit
migration instructions exist; do not assume arbitrary runtime schemas can be resumed across releases.

In the harness checkout, fetch tags, check out the selected version, reinstall with the same `pip install` command,
and rerun the Cursor sync script after directory/skill changes. Restart Cursor. Its junctions reference the
checkout directly, so changing branches also changes the code and policies used by the hooks.

To uninstall Cursor integration, run from the same checkout:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/uninstall-from-cursor.ps1
```

Backups remain for manual restoration. Restart Cursor to unload hooks. Separately uninstall the CLI:

```sh
python -m pip uninstall agent-loop
```

Project memory, plans, archives, and experiment evidence belong to the project and remain available.
