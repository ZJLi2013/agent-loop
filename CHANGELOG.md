# Changelog

All notable user-facing changes are documented here. This project follows Semantic Versioning.

## [Unreleased]

### Added

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

### Changed

- Project runtime moved from `.cursor/` to `.agent-loop/`, with read compatibility for existing projects.
- Policies and hook actions moved behind platform-neutral `skills/` and adapter protocol boundaries.
- Reviewer dispatch moved from a stop-hook instruction to the verifier orchestration; execution and next-task
  initialization remain blocked until the reviewer writes a decision.
- Reviewer dispatch uses submitted Plan Revisions and verified tasks as its two decision boundaries; individual
  edits do not trigger review, and model CLI sessions and caches remain outside agent-loop project state.
- Memory CLOSE now retires successful experiment history already carried by project documents, keeps
  `disproved` / `rejected` decisions, and migrates maintained legacy memory to `.agent-loop/memory/`.

### Fixed

- Workspace fingerprint skips nested `.codex/` scratch directories, whose locked files crashed verify on Windows.
- Closed-task archiving no longer drops a row whose task id was already used by an earlier Goal.

[Unreleased]: https://github.com/ZJLi2013/agent-loop/commits/main

