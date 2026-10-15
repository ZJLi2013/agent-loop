# Changelog

All notable user-facing changes are documented here. This project follows Semantic Versioning.

## [Unreleased]

### Added

- On-demand `research-to-paper` skill: an arXiv-style paper and an optional 5–15 s teaser from a closed research
Goal, with every number traced to the experiment records. Usage documents how to invoke on-demand skills.

### Changed

- Plan review is per task instead of per Plan Revision. A task is sent to the reviewer only when it is new or its
  design digest changed (title, checkpoint, and the design sections the checkpoint links; not priority, `rev`,
  status, or row order), and each task gets its own `accept` / `revise`. A task sent back with `revise` whose design
  then changes waits for the human: `plan-review --approve <task> --reason` binds approval to its current digest,
  `--again <task> --reason` allows one more review. A successor written by the task reviewer counts as reviewed.
  The reviewer report now maps task ids to verdicts. This replaces the per-revision records, the brake, and the
  waiver; a failed review is no longer cached. Open tasks have no per-task verdict yet and are reviewed once.

- After the task reviewer chooses `ask_human` or `stop`, `init` starts the next task once the plan is at a newer
  Plan Revision marked `approved`, instead of requiring `disable` first.

- A task-boundary review decision is valid only after the closed task's headed sections leave the active plan
  document; the reviewer moves them to a sibling `<plan>-archive.md`, and a failed re-review can no longer fall
  back to the previous decision while those sections remain.
- Both reviewers take criteria only from the Goal, the listed repo checklist and checklists the design links;
  `archive/` content is history, not a criterion. Evidence is limited to the listed inputs, files the plan,
  task list or design links directly, and the code under test the design names; reviewers report missing
  evidence instead of searching and stop reading once they can decide.
- Reviewer prompts live in `harness/prompts/plan_review.md` and `harness/prompts/task_review.md` and ship with
  the wheel; rendered prompts are unchanged.
- Usage recommends an editable CLI install for Cursor enforced mode, so the CLI and the linked hooks run the
  same checkout. `sync-to-cursor.ps1` warns when the CLI is not installed from that checkout.

### Fixed

- A verified task no longer enters Goal Review when it sits idle past the timer or the context is compacted.
  The completion gate hands it to the reviewer or the human instead of pausing it, which used to send it back to
  `ready` and clear its verification.
- A session no longer pauses or prompts about another session's task. `init` records the session id
  (`AGENT_LOOP_SESSION_ID`, else `CURSOR_CONVERSATION_ID`) as the task's `owner`; the completion gate and
  COMPACT skip tasks owned by a different session, and a request without a session id counts as a different
  session. State written before this change has no owner and is handled as before.
- A Cursor conversation is bound to every project whose task list it reads, not only the first one, so the
  completion gate follows work that moves to another project in the same workspace.

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

