# Minimal project

Copy `task.md` to `.cursor/task.md` and use `plan.md` as the reviewed plan document.

```powershell
mkdir .cursor
copy examples\minimal-project\task.md .cursor\task.md
python $env:USERPROFILE\.cursor\harness\run.py init --task t1 --plan-doc plan.md `
  -- python -c "print('verification passed')"
python $env:USERPROFILE\.cursor\harness\run.py verify
```

The `Plan Revision` in `plan.md`, task `rev`, and Harness runtime revision must match.

