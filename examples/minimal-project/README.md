# Minimal project

Copy `task.md` to `.agent-loop/task.md` and use `plan.md` as the reviewed plan document.

```powershell
mkdir .agent-loop
copy examples\minimal-project\task.md .agent-loop\task.md
agent-loop-harness init --task t1 --plan-doc plan.md `
  -- python -c "print('verification passed')"
agent-loop-harness verify
```

The `Plan Revision` in `plan.md`, task `rev`, and Harness runtime revision must match.

