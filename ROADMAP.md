# Roadmap

The roadmap describes direction, not delivery dates. Concrete work belongs in GitHub Issues and Milestones.

## Now

- publish and validate the v0.1 public-project baseline;
- test clean install/uninstall on supported Windows and Cursor versions;
- stabilize Harness config/state schema and migration rules;
- collect real project feedback on review, pause, verifier, and Goal Review behavior.

## Next

- add a task decision contract (`pass`, `fail_to`, `budget`) and block `READY` until all three are valid;
- route expected negative results to an explicit next task/action instead of relying on generic DIAGNOSE;
- add a supported macOS/Linux sync path;
- add installer dry-run and diagnostics;
- publish minimal-project and policy/adapter examples;
- define compatibility fixtures for future Cursor hook payload changes.

## Later

- evaluate an external driver for complete tool-call control outside Cursor;
- evaluate BOUND or another supervisor instead of duplicating external-agent orchestration;
- add project profiles only when multiple real projects need different policies.

## Non-goals

- task or hypothesis DAGs;
- a dynamic plugin framework;
- silently controlling Cursor tool calls that were not delegated to the Harness runner;
- roadmap commitments based only on speculative feature requests.

