# Case studies

[Project](../en.md) · [Study map](../docs/study/README.md)

These Chinese-language notes record specific runs and maintenance incidents. They explain design choices;
they are not controlled benchmarks or guarantees of performance on other projects.

| Case | What it illustrates |
|---|---|
| [RoboJEV × Nox](robojev-nox.md) | Worker/reviewer decisions across task boundaries |
| [Record growth](agent-loop-record-growth.md) | Cross-session records and why they need a retirement policy |
| [Plan growth](robojev-plan-growth.md) | Why a reviewer-maintained plan grew with every closed task, and what a CLOSE guard must check |
| [RoboTwin memory](robotwin-memory-consolidation.md) | Consolidating project memory |
| [Chained tasks](wmforge-r8-chained-tasks.md) | How task chaining bypassed design/review boundaries and motivated a guard |
| [Review loop](robotrsi-vla-review-loop.md) | Why one plan-review gate for every task cost more than it found on cheap CPU probes (open) |
| [Session scope](cursor-session-scope-binding.md) | How first-read session binding pointed the completion gate at the wrong project, surfaced another session's lock as a gate failure, and let one session pause another session's task (open) |
| [Stale runner lock](robotrsi-stale-runner-lock.md) | Why an aborted runner left a stale lock, a phase stuck in running, an empty journal, and an orphaned remote job (open) |
| [Run artifact retention](harness-vla-run-artifact-retention.md) | Why a rule-compliant CLOSE self-audit left 98 MB of run output beside the experiment doc: "keep raw output" has no criterion, location, or retention period |

Current behavior is defined in [design.md](../design.md), rather than reconstructed from historical cases.
