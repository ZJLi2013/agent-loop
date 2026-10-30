# Changelog

All notable user-facing changes are documented here. This project follows Semantic Versioning.

## [Unreleased]

### Added

- Shared memory root: when `AGENT_LOOP_SHARED_MEMORY` names a directory with an `INDEX.md`, the memory hook injects
  that index after the project's memory on every `task.md` read, including in projects without `memory/`, and appends
  one line per injection to `~/.agent-loop/shared-memory-arrivals.jsonl`. Unset, the hook behaves as before. See
  `skills/agent-memory/SKILL.md`.

- Skill packs: any directory with a `pack.toml` can be listed in a machine-local `~/.agent-loop/packs.txt` together
  with the repository checkouts it refers to and the active profiles. `scripts/install-skills.py`, called by both
  `sync-to-cursor.ps1` and `sync-to-dsh.ps1`, links agent-loop's skills and the selected pack skills (Cursor:
  `~/.cursor/skills`). A pack skill whose name is taken or whose target is occupied is skipped and the installer
  exits non-zero. `requires` names a skill of agent-loop or of any registered pack; a missing, unselected, skipped or
  cyclic provider skips its direct and indirect dependents, providers are linked first, and a provider that fails to
  link skips its dependents, keeps their existing links, and does not abort the run. A skill moved from agent-loop into a pack switches over in one
  run. Only links into registered sources are ever removed. agent-loop skill names are now a public interface: a rename or removal is announced here and kept for one
  release. See `docs/usage.md#skill-packs`.

- Harness owns task scratch: `init` creates `.harness/tasks/<task_id>/` for kits, workspaces, local run outputs, job
  lists and PR drafts, and removes it after the reviewer's decision is saved; projects without a reviewer run
  `clean-task` at CLOSE. A removal failure is reported, not raised. `init` and `status` list `strays`: `.harness/`
  entries Harness does not own and scratch directories of other tasks.
- `task.md` holds the whole backlog: besides the next 1–2 tasks, an optional `## Candidates` table (priority,
  title, entry condition) and a `## Triggered` list ("when <event>: <action>"). The plan document keeps only the
  Goal, boundaries, current conclusion and its evidence.
- The small-change exemption is judged per project: once a project without a plan Goal has had its rules, schema
  or pipeline changed under the exemption, the next such change starts with a Goal and the Human Review Gate. A Goal
  whose output has a reader names that reader and includes one hand-written sample of the final output.
- A Goal change or `replan` also marks each design and evaluation set derived from the old Goal keep, revise or
  drop in the plan; the human decides on the ones the human proposed. Labels gathered for the old question are not
  acceptance evidence for the new Goal unless the plan states why the question is unchanged.
- Planning and experiments follow the cost of being wrong: reversible changes such as prompts and thresholds ship
  and are judged on production signal, offline validation is kept for hard-to-reverse decisions, and labels gathered
  for a different question count as a failed proxy. A human's implementation proposal is adopted by default and
  checked against the Goal like the agent's own; on a conflict, including after the Goal changes, the agent points
  it out and the human decides whether to change or keep it. Designs start with a search of rejected
  approaches, pipelines run a thin end-to-end slice first, backtests keep the tested samples out of context, and
  dependent tool calls are issued in sequence.
- `task.md` can hold a `## 主线` section: one line for the mainline and an ordered table of Goals marked
  `✅ done`, `▶ next` or `⬜ todo` (format in `task-state`). When the reviewer stops a mainline Goal, the agent marks
  it done and starts the `▶ next` Goal with its own plan and plan review, also when unattended, provided the human
  approved the table (`Mainline Review: approved`). Adding, dropping or reordering Goals goes back to the human.
  Archiving no longer moves the table's `✅ done` rows out of `task.md`.
- `.github/auto-fix/run.ps1` hands one open `auto-fix` issue to Codex in its sandbox, following
  `.github/auto-fix/agent.md`, and marks the resulting pull request ready only if CI fails on the regression test
  alone and passes with the fix. It then reverts the test, so only the fix is merged; the maintainer merges it.
  `self-report` adds the `auto-fix` label only to Kernel and Adapter bugs, and the agent stops on proposals and
  Policy wording.
  `AI_POLICY.md` exempts this output and `from-agent` issues from review before submission and requires them to say
  so.
- `self-report` skill: when a Harness command fails or refuses, two rules conflict, or a correction traces to
  agent-loop wording, the agent files an issue here with a file and line, the expected and actual behaviour, and a
  reproduction built only from public agent-loop material. `check_report.py` blocks local paths, host names, the
  GPU models listed in `external-output-boundary`, credentials and transcripts, and requires an AI-use line; a
  blocked or over-limit report is saved under `.agent-loop/reports/` instead. It catches only defects with a visible
  signal; `CONTRIBUTING.md` lists what it misses and when to open an issue yourself.
- `CONTRIBUTING.md`: a rule, skill, or reviewer-prompt change that changes a decision is accepted by a behavior
  replay. The pull request states the decision as a contract, replays a few synthetic scenarios plus one control on
  the base branch and with the change, and records the model, inputs, and expected and observed actions. A check
  that the prompt contains a sentence is not evidence; wording that changes no decision needs no replay.
- On-demand `code-to-uml-diagram` skill: a Mermaid class diagram of a class and its direct collaborators, with
  inheritance, composition, injection and construct-then-register each read from one kind of source line, plus
  one sequence diagram per key scenario whose participants come from the class diagram.
- On-demand `research-to-paper` skill: an arXiv-style paper and an optional 10–15 s teaser from a closed research
Goal, with every number traced to the experiment records. The agent builds teasers with onetake, whose usage notes
the skill records; a human-recorded UI walkthrough uses a screen recorder such as Recordly. Usage documents how to
invoke on-demand skills.
- dsh (DeepSeek Harness) enforced adapter: through dsh's `hooks-codex` bridge, a dsh worker is held by the
  completion gate until the task is verified, and the memory index is injected at session start.
  `scripts/sync-to-dsh.ps1` renders the always-apply rules into `$DSH_HOME/AGENTS.md` and links the skills into
  `$DSH_HOME/skills`. `reviewer.json` can point at dsh headless running a different model. `init` records
  `DSH_SESSION_ID` as the task owner. The model stays the host's provider config; usage covers configuring one.

### Changed

- The plan's `## 脉络` holds one row per stage (`| 阶段 | 问了什么 | 结论 | 带来的改变 |`): a run of tasks answering
  one question, or one Plan Revision. At a task boundary the reviewer extends the current row and opens a new one only
  when the next command changes direction: a new question, a disproved hypothesis that changes the approach, a
  replan, a human correction, or a stop. Cells carry no readings or links; per-task evidence stays in the
  Experiment Log and its archive. Existing per-task threads stay valid; a project can fold one once by moving its
  rows verbatim under 「脉络原文」 in `<plan>-archive.md`.
- Code work that introduces a new abstraction, adds a second implementation of a concept the codebase already has
  (a check, a state reader, a registry), or changes an interface used across modules writes a class-level design
  before its tasks are split: current and target class diagrams, one sequence diagram, one owner per concept, and the
  smallest mergeable migration order (`work-planning` step 2). It is the first task's design, so that task's plan
  review is the architecture review; later tasks wait until it closes. The plan reviewer reports a code task that
  adds such a second implementation without a class-level design naming the single owner as must.
  `code-to-uml-diagram` is no longer deprecated: it now loads in the loop for this design, and marks the new or
  changed parts of a target diagram as `<<proposed>>`.
- The task reviewer can choose `revise` when the verified task's own CLOSE is unfinished: a project fact it
  established is only under `.agent-loop/`, or the design's closing step was skipped. Harness keeps the task open
  and its scratch in place, allows only the runner and verify, and refuses init and `clean-task` until the next
  verify is reviewed. A task can be sent back once; a second `revise` counts as an invalid decision. Gaps in other
  tasks before `stop` still become a new closing task. The review record gains `revised_run`; state written before
  this release has none and behaves as before.
- Admission: issue forms and the pull request template ask which public guarantee a change maintains, and blank
  issues are off. The maintainer triages each open issue weekly as `restores-contract`, `changes-contract` or
  `out-of-scope`; contract changes merge any time while agent-loop has no outside users and on window days, every
  fourth Monday from 2026-11-02, once a fork or an outside issue or pull request appears, and
  `.github/auto-fix/run.ps1` takes only issues triaged `restores-contract`. See `CONTRIBUTING.md#admission`.
- A project's facts and conclusions live in its own tracked documents; the plan document holds the active Goal's
  working conclusions and links to them, and memory holds runtime facts, rejected options and pointers. Before the
  locked verifier the worker writes the facts a task established into the project's documents, and the task reviewer
  reports a fact found only under `.agent-loop/` or `.harness/` as must and does not stop a Goal until all of its
  facts have landed.
- Comparison experiments run every arm once on the smallest case before the full batch (`experiment-design`
  Phase 1.5), and the plan reviewer checks the design for that step. While a batch runs, `when-to-stop` stops the
  remaining jobs as soon as they can no longer change the planned next command, for example when the acceptance
  check is already decided or the control arm failed everywhere.
- Planning: the design of a task that changes code names the existing owner it lands in, the mechanisms it reuses,
  the files it changes and the test pinning each behavior; the module contract is the expanded form for risky changes.
  Plan review reports a missing owner or a parallel mechanism as revise, and checks the call chains, records and
  boundaries the design says exist against the code, reporting a mismatch as must.
- Installing skills: a plain directory with the name of an agent-loop skill in the host's skill directory is reported
  as a conflict and the installer exits non-zero; the directory is left untouched. On dsh it used to be moved to
  `skills-backup-<time>`; on Cursor it was left in place silently and shadowed the agent-loop skill. Dead links that
  do not point into agent-loop or a registered pack are no longer pruned; they are listed as `unmanaged`.
- A change that adds state persisting across runs, a read/write or permission boundary, concurrent writers, or an
  interface with more than one caller gets a one-page module contract in its task design before code: owner,
  data lifecycle, read/write modes, invariants each paired with a test, concurrency and failure behaviour, and
  non-goals. The human reviews its invariants and trade-offs, the plan reviewer asks for a revision when the
  contract or an invariant's test is missing, and `minimal-code` routes such a change there instead of treating the
  structure as speculative abstraction.
- The CLOSE self-audit decides the fate of what the task created on a remote node: containers, checkouts, venvs
  and build directories, run outputs, and images and weights pulled only for it are classified by the `remote-exec`
  storage tiers; one-off ones are deleted and kept ones go into `facts.md` with their path and purpose. Only the
  container names and work directories recorded in the handoff note are claimed, so shared caches and other users'
  containers are never touched. The handoff note records those container names and work directories.
- Durable records have a home. A plan document inside `.harness/` is rejected by `init`, `resume` and
  `plan-review`. Auto-Stop Reports, overnight reports and pending `⚠️ 待确认` items go into the processed
  project's `.agent-loop/progress.md` handoff. `remote-exec` reads and records GPU occupancy in `facts.md`.
  Evidence that must outlive the runtime is copied into the per-run table instead of citing `runs.jsonl` lines or
  `artifacts/`, which Harness truncates and prunes. `experiment-design` states that gitignored document
  directories are outside the evidence fingerprint.
- A task design lives in the plan document (a heading section that starts with the task id) or a linked sub-exp,
  never under `.harness/tasks/`, which is deleted when the task closes. The task reviewer is told so when it writes
  the next task, and the plan reviewer asks for a revision when a design sits there.
- `remote-exec`: the agent picks the node itself by the section 2 score instead of asking the human. Before
  scoring it excludes GPUs that `rocm-smi --showpids` shows busy or that another project's handoff note claims,
  and records the chosen node and GPUs in its own handoff. The batch-run report follows the target project's
  output format (for example one card per repo) when the project defines one.
- The plan document keeps one append-only `## 脉络` table, one row per closed task and per `Plan Revision`, saying
  which next command or Goal change each step caused. Whoever makes the decision writes the row; CLOSE, replan and
  Goal freeze keep it. It replaces the `下一步决策` section and the task pointer rows in the Experiment Log, and the
  task reviewer puts its caveats in the `review` field instead of 「当前结论」.
- A change made only to test a hypothesis stays in the experiment kit (flag, monkeypatch or scratch entry point)
  without a PR until the result is positive; a positive result reaches product code as its own task and PR, and the
  plan reviewer flags checkpoints that require merging the code under test.
- Goal attention no longer pauses on failures or stale evidence, and action/time pauses are opt-in. Stale evidence
  keeps the task failed and points directly to the locked verifier.
- Cursor's first `preCompact` hook event tells the user when a context window below one million tokens compacts
  and suggests switching to a 1M-context model. Compaction no longer pauses the Harness for Goal Review.
- `upstream-contribute` looks for the upstream's own agent skills. A PR-writing skill shapes the body and its
  checks run before posting. When the upstream ships a review skill, the PR opens as a draft, the agent runs that
  skill from the upstream default branch, fixes the findings that hold up, answers the ones that do not in the PR
  body with evidence, and then tells the user to mark it ready.
- Following up an upstream PR, the agent may fix and verify on its own, but pushes, replies and thread
  resolutions wait for the user; `autopilot` replies and resolves threads by default.
- Experiment scripts stay only while a kept script, the next approved task, or another Goal consumes them; scripts
  reused across Goals become stable entries with tests. One-off scripts are deleted once their parameters and input
  construction rules are in the document, and Goal CLOSE deletes those referenced only by that Goal's documents.
- Experiment run output no longer stays beside the experiment document. CLOSE writes a per-run table of what the
  conclusion, verifier and reviewer read into the document, keeps run directories outside it, deletes runs the
  conclusion excludes, and deletes the task's run directories at task CLOSE. Sub-experiment documents stay immutable.
- The runner writes raw command output under the run directory instead of the system temp directory, which an
  agent sandbox (dsh on Windows) may not let the command's identity write.
- Study notes moved to `docs/study/<feature>/`; `docs/usage.md` is now in Chinese.
- A run whose runner process was killed no longer blocks the task. The next `exec`, `verify` or completion gate
  marks it `failed`, adds an `aborted` entry with its command and start time to `runs.jsonl`, and reports that
  the command may have finished or may still be running remotely, so its outputs should be checked before it is
  run again; the next `exec` runs normally. Each run directory now starts with `start.json`. A task or plan
  reviewer whose process is gone no longer blocks another review.

- Plan review is per task instead of per Plan Revision, and each task is reviewed once: when it first appears,
  all unreviewed tasks go to the reviewer in one call, and later design edits do not trigger another review
  (`plan-review --again <task>` asks for one). Reviewer items follow a must / suggest protocol: `must` means the
  task goes the wrong way, reaches a wrong conclusion or wastes an expensive run if ignored, and needs a stated
  consequence and evidence, otherwise it counts as `suggest`; at most 3 of each are kept. The executor answers
  every `must` with `plan-review --respond <task> --item N=applied` or `N=reject --reason "<fact>"` before
  `init`; `suggest` items may be skipped. A `must` marked `human: true` waits for `plan-review --approve`. This
  replaces the per-revision records, the brake and the waiver; a failed review is no longer cached. Open tasks
  have no per-task review yet and are reviewed once.

- The task reviewer only judges. It writes its decision, must / suggest `findings` and its review notes;
  Harness marks the task done, moves its plan sections to `<plan>-archive.md` with a pointer left behind, and
  rewrites links to the moved anchors, including links in task rows moved to `archive/tasks.md`, which used to
  break. `init` accepts any human-approved `doing` task rather than only the reviewer's pick. Unattended
  (`Plan Review: unreviewed`), it starts only the task the reviewer names: the `next_task` of `continue`, or of
  `ask_human` when the question does not affect it; nothing after `stop`.

- Both reviewers take criteria only from the Goal, the listed repo checklist and checklists the design links;
  `archive/` content is history, not a criterion. Evidence is limited to the listed inputs, files the plan,
  task list or design links directly, and the code under test the design names; reviewers report missing
  evidence instead of searching and stop reading once they can decide.
- Reviewer prompts live in `harness/prompts/plan_review.md` and `harness/prompts/task_review.md` and ship with
  the wheel; rendered prompts are unchanged.
- Usage recommends an editable CLI install for Cursor enforced mode, so the CLI and the linked hooks run the
  same checkout. `sync-to-cursor.ps1` warns when the CLI is not installed from that checkout.

### Deprecated

- `remote-exec` leaves agent-loop in the next release: it depends on a personal node pool, which `design.md#范围`
  places in a private pack, and the maintainer's private pack will provide it under the same name. To keep using it,
  copy `skills/remote-exec` from this release into a pack of your own and list that pack in `~/.agent-loop/packs.txt`;
  `requires = ["remote-exec"]` then resolves to it unchanged. Core rules and skills no longer route to it:
  `agent-heartbeat` states its own `<log>.exit` launch contract, and the `experiment-design` CLOSE self-audit carries
  the remote asset rules. Fail-fast for detached batches (#107) belongs to that pack.
- Six on-demand skills leave agent-loop in the release after the one carrying this notice: `code-review`,
  `code-to-kernel-diagram`, `gen-ppt`, `research-to-blog`, `research-to-paper` and `upstream-contribute`. None is part of the task lifecycle, so `design.md#范围` places them in an external pack. They
  ship and are maintained as before until then. The maintainer's private pack will provide them under the same
  names; it is not public. To keep using one after removal, copy `skills/<name>` with its resource files from this
  release into a pack of your own and list that pack in `~/.agent-loop/packs.txt`; rerunning the installer switches
  the link over. Until removal a pack skill with the same name is skipped as a name conflict. None declares
  `requires`, and the names stay unchanged, so a `requires` on them resolves to your pack. Before removal, core rules
  and skills stop naming them; the per-skill list is in `docs/study/skill-migration.md`.

### Removed

- `case_study/`. Problems found while running agent-loop are reported as issues instead.

### Fixed

- Passing Harness verification no longer consumes `max_attempts`, so stale evidence can be verified again.
  Failed verification (including output-contract rejection) still consumes the attempt budget; wall time remains bounded.

- A task design written under a topic heading such as `### Data cleanup (a1)` stayed in the active plan forever, since
  CLOSE archives only sections whose heading starts with the task id. `init --plan-doc` now refuses a task unless every
  link from its `task.md` row into the plan lands in such a section (by GitHub heading slug or an `<a id>` before it)
  and at least one link locates the design there or in a file under the plan's directory, such as `sub-exp/`.

- A successor task written by the task reviewer goes through plan review before `init`, like any other task; it no
  longer counts as reviewed because the task reviewer named it. `init` runs that plan review itself, also under
  `Plan Review: approved`, and starts the task once its `must` items are answered and no item awaits the human.
  Records left by that shortcut count as not reviewed.
- On Windows, Harness state writes wait up to about one second for a reader that has the file open (a hook reading
  `state.json` while the runner writes it), instead of failing with `WinError 5`. A failed write leaves no temporary
  file behind.
- A task whose plan-review record file belongs to another task id is refused with "rename the task". On Windows and
  macOS, ids that differ only in case (`t1`, `T1`) share one file; a new `t1` used to inherit `T1`'s review and
  skip the reviewer.
- A plan review counts only for the plan document it reviewed. A task id reused under another Goal's plan is
  reviewed again instead of inheriting the old task's review; reviews recorded before this change count for the
  current plan.

- Completion checks honor the review of a verified task before validating its plan, so deleting the plan
  during cleanup does not block completion or the reviewer's next-task handoff.

- A busy state lock now waits a few seconds, then names its holder (pid, command, start time). When the holder
  is gone, the error includes the command that removes the stale lock; Harness does not remove it itself. Lock
  files written before this change, which hold only a pid, read the same way.
- Commands and reviewers no longer hold the state lock while they run. A running exec or verify is marked in
  `state.json` (run id and runner pid), a task review in `review_running`, a plan review in
  `plan-review/running.json`; `status`, `pause` and the completion gate keep working meanwhile, and a second run
  is refused with the running one's id. The gate reports a `running` phase instead of marking it interrupted.
- A verified task no longer enters Goal Review when it sits idle past the timer or the context is compacted.
  The completion gate hands it to the reviewer or the human instead of pausing it, which used to send it back to
  `ready` and clear its verification.
- A session no longer pauses or prompts about another session's task. `init` records the session id
  (`AGENT_LOOP_SESSION_ID`, else `CURSOR_CONVERSATION_ID`) as the task's `owner`; the completion gate and
  COMPACT skip tasks owned by a different session, and a request without a session id counts as a different
  session. State written before this change has no owner and is handled as before.
- A Cursor conversation is bound to every project whose task list it reads, not only the first one, so the
  completion gate follows work that moves to another project in the same workspace.
- `gen-ppt` connectors drawn with `arrow()` render with an arrowhead.

## [0.1.0] - 2026-10-12

### Added

- English entry documentation, a failing-to-passing quickstart, release guidance, and a sourced related-project comparison.
- Isolated sdist/wheel installation smoke covering public CLI verification, repair, stale evidence, and uninstall.

- Apache-2.0 licensing and public contribution, security, AI-use, and conduct policies.
- GitHub issue/PR templates and cross-platform Harness CI.
- Windows uninstall support.
- Stable Kernel / Policies / Adapters architecture.
- Reviewed plan documents with revision-bound tasks.
- Bounded command runner, execution journal, independent verifier, and Cursor completion gate.
- Runtime pause/resume and event-driven Goal Review.
- Project memory with forced retrieval through a Cursor hook.
- Plan-boundary reviewer: each submitted Plan Revision receives one advisory review before human approval;
  initialization, resume, pager approval, and unattended activation all enforce the report.
- Task-boundary reviewer: after verification, the Harness automatically runs a configurable reviewer command
  (`.agent-loop/reviewer.json`), which rewrites the next task and decides `continue`, `ask_human`, or `stop`.
- Human checkpoints on the phone: with `.agent-loop/pager.json`, plan approval, reviewer `ask_human`, reviewer
  failure, and budget exhaustion are paged through the pager CLI, and the reply maps to a Harness action.
- `tools/pager`: the email pager ships in this repository as its own package; the Graph client is injected
  through `PAGER_GRAPH_SCRIPTS`.
- Record lifecycle policy: task / Goal CLOSE promotes current conclusions while moving closed tasks, old
  handoffs, and superseded experiment summaries out of the default context into linked archives.
- CLOSE self-audit: before the locked verifier, the worker rereads the task diff, removes transitional
  documentation and one-off scripts, and leaves only durable facts, decision analysis, conclusions, and evidence.
- Domain research for research-type experiments: the design template asks for field precedent before the run,
  negative or surprising results are compared with field conclusions, and both reviewers check for it.
- Content review: both reviewers check the task's material under test (questions, data, samples, requests)
  against the Goal, using rendered samples rather than prose; the task reviewer maps a mismatch with the design
  to `ask_human`. An optional per-repository `.agent-loop/review-checklist.md` is listed as reviewer input.

### Changed

- Project runtime moved from `.cursor/` to `.agent-loop/`, with read compatibility for existing projects.
- Policies and hook actions moved behind platform-neutral `skills/` and adapter protocol boundaries.
- Reviewer dispatch moved from a stop-hook instruction to the verifier orchestration; execution and next-task
  initialization remain blocked until the reviewer writes a decision.
- Reviewer dispatch uses submitted Plan Revisions and verified tasks as its two decision boundaries; individual
  edits do not trigger review, and model CLI sessions and caches remain outside agent-loop project state.
- Reviewer-selected successor tasks remain `📝 proposed` and require explicit activation as `🔬 doing`
  before initialization.
- Memory CLOSE now retires successful experiment history already carried by project documents, keeps
  `disproved` / `rejected` decisions, and migrates maintained legacy memory to `.agent-loop/memory/`.
- The focused minimal-code rule replaces the vague KISS rule and rejects speculative abstractions, fallback
  paths, compatibility shims, and unrelated cleanup during implementation.

### Fixed

- Workspace fingerprint skips nested `.codex/` scratch directories, whose locked files crashed verify on Windows.
- Closed-task archiving no longer drops a row whose task id was already used by an earlier Goal.
- Cursor lifecycle hooks bind each conversation to the first project task it reads, preventing STOP and
  preCompact events from affecting projects owned by other sessions.

[Unreleased]: https://github.com/ZJLi2013/agent-loop/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/ZJLi2013/agent-loop/releases/tag/v0.1.0

