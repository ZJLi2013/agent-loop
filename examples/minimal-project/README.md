# Minimal project

This fixture contains an intentionally incorrect arithmetic mean and two acceptance tests. Use the
[quickstart](../../docs/quickstart.md) for the complete install, expected failure, repair, and verification walkthrough.

From the agent-loop repository root:

```sh
python examples/minimal-project/prepare.py ../agent-loop-demo
cd ../agent-loop-demo
```

`prepare.py` copies the code and reviewed plan, places the task at `.agent-loop/task.md`, and refuses to overwrite
an existing directory. Work in this copy; keep the repository fixture failing so the installation smoke can test it.

The fixture has matching plan revision `1` and task `r1`. Its pre-approved status applies only to this walkthrough.
No model, API key, or reviewer is configured.
