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
- Task-boundary reviewer: after verification, a configurable reviewer command (`.agent-loop/reviewer.json`)
  rewrites the next task and decides `continue`, `ask_human`, or `stop`.
- Human checkpoints on the phone: with `.agent-loop/pager.json`, plan approval, reviewer `ask_human`, reviewer
  failure, and budget exhaustion are paged through the pager CLI, and the reply maps to a Harness action.
- `tools/pager`: the email pager ships in this repository as its own package; the Graph client is injected
  through `PAGER_GRAPH_SCRIPTS`.

### Changed

- Project runtime moved from `.cursor/` to `.agent-loop/`, with read compatibility for existing projects.
- Policies and hook actions moved behind platform-neutral `skills/` and adapter protocol boundaries.

### Fixed

- Workspace fingerprint skips nested `.codex/` scratch directories, whose locked files crashed verify on Windows.

[Unreleased]: https://github.com/ZJLi2013/agent-loop/commits/main

