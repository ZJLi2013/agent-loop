# Roadmap

The roadmap describes direction, not delivery dates. Concrete work belongs in GitHub Issues and Milestones.

## Now: v0.2 exploration mode

The current loop is a confirmation mode: one `doing` task, plan revisions, a locked verifier and admission
review keep engineering iterations from drifting. Run against an open research question, the same invariants
turn the work into a walk from one cheapest candidate to the next, and review cost can exceed the experiment
it gates. Exploration mode runs **in parallel with** the confirmation loop, as a peer mode with opposite
invariants, not as a step inside it. Design proposal: [exploration-mode.md](docs/study/exploration-mode/exploration-mode.md);
survey and decision table: [research-automation.md](docs/study/exploration-mode/research-automation.md).

Order of work:

1. **Survey before design.** Study how research-automation and self-iterating systems handle open problems
   without an evaluator: autoresearch, AlphaEvolve, AI Scientist-v2, AI co-scientist, and RSI-adjacent work
   such as the Darwin Gödel Machine. Extract when they branch, how they rank and prune, when they build an
   evaluator first, and where the human decides. The result is the design basis for the mode in general, not
   a fix for one project.
2. **Research map and exploration policy, separate from the confirmation loop.** One page per root question:
   a progress signal validated before any search, competing branches, cheapest decisive probe, falsification
   condition, budget ([template draft](docs/study/exploration-mode/research-map-template.md)). A new skill owns the policy. The
   confirmation loop's plan, review, Harness gates and their behaviour do not change; the two modes share only
   common pieces — budget declarations, evidence on disk, project memory, heartbeat, pager, and an advisory
   reviewer. **Entry routing:** the agent proposes a mode for a new Goal against the promotion conditions, and
   the human decides.
3. **Cost-proportionate brake** (done, confirmation side). Warn, without blocking, when a plan is sent back for
   revision 3 times in a row or 3 revisions pass without an experiment.
4. **Promotion to confirmation mode.** A branch that meets the promotion conditions is handed over in the
   existing plan format — a proposed Goal and first task with one unverified hypothesis, acceptance checkpoint,
   failure route and budget — and enters the unchanged plan review and human approval. In exploration mode an
   expected negative result prunes a branch instead of entering generic DIAGNOSE.

Acceptance:

- Replay roboJev Stage 1.5 as the test subject, using only what was known before it started: the first cycle
  ranks an oracle upper-bound scan, or reuse of an environment with known natural failures, ahead of building
  a new carrier.
- Run one new real exploratory Goal and record revisions per experiment and time to the first decisive probe.
- If neither improves on the confirmation-only path, stop adding exploration features.

Not in v0.2: parallel probe orchestration (it would approach the task-DAG non-goal), automatic large-scale
hypothesis generation or tournament ranking, and self-improvement of the Harness itself.

## Ongoing: v0.1 follow-through

- test clean install/uninstall on supported Windows and Cursor versions;
- stabilize Harness config/state schema and migration rules;
- collect real project feedback on review, pause, verifier, and Goal Review behavior.

## Next

- add a task decision contract (`pass`, `fail_to`, `budget`) and block `READY` until all three are valid;
- add a supported macOS/Linux sync path;
- add installer dry-run and diagnostics;
- publish minimal-project and policy/adapter examples;
- define compatibility fixtures for future Cursor hook payload changes.

## Later

- generalize external tools: reviewer (`.agent-loop/reviewer.json`) and pager (`tools/pager`, `.agent-loop/pager.json`) are both
  config-declared commands locked at init and invoked at a lifecycle point (task boundary, human checkpoint);
  fold them into one registry of `{lifecycle point, argv, input contract, output contract}` once a third tool
  appears — declared commands, not a dynamic plugin loader;
- evaluate an external driver for complete tool-call control outside Cursor;
- evaluate BOUND or another supervisor instead of duplicating external-agent orchestration;
- add project profiles only when multiple real projects need different policies.

## Non-goals

- task or hypothesis DAGs (a research map is a document, not a scheduler);
- a dynamic plugin framework;
- silently controlling Cursor tool calls that were not delegated to the Harness runner;
- roadmap commitments based only on speculative feature requests.
