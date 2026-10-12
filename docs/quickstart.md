# Quickstart: a failing test, a repair, and verified evidence

[中文入口](../README.md) · [English entry](../en.md) · [Usage](usage.md)

This walkthrough exercises the CLI without a model, API key, reviewer, or host hooks. You act as the worker.
It uses a disposable project with an intentionally broken arithmetic mean. The example plan is pre-approved
for this walkthrough; real project plans need your review.

## 1. Install and create the example

Requirements: Python 3.11+, pip, and Git. Run each command separately in Bash or PowerShell; use `python3`
where needed. A virtual environment is recommended. On distributions with externally managed Python,
create and activate a venv before installing (install your OS's Python venv support if necessary).

```sh
git clone https://github.com/ZJLi2013/agent-loop.git
cd agent-loop
python -m pip install .
agent-loop-harness --help
python examples/minimal-project/prepare.py ../agent-loop-demo
cd ../agent-loop-demo
```

If a published version is desired, check out its tag before installing. The preparation script refuses to
overwrite an existing destination. Use another new directory when repeating the walkthrough.

If the CLI is not on your PATH, use `python -m harness.run` in place of `agent-loop-harness` throughout.
Keep using the interpreter/environment into which you installed the package.

## 2. Lock the verifier and observe a real failure

```sh
agent-loop-harness init --task t1 --plan-doc plan.md -- python -B -m unittest -v
agent-loop-harness verify
```

The first `verify` intentionally exits **1**. `average([1, 2])` returns `1` instead of `1.5`.
The JSON result reports `outcome: fail`; failure also requests a Goal Review before another action.
The `-B` flag avoids bytecode files becoming incidental workspace changes in this small example.

```sh
agent-loop-harness status
```

Inspect `.harness/runs.jsonl` and `.harness/artifacts/<run_id>/stderr.log`. The test output appears in stderr
because Python's unittest runner writes there. The runtime directory also contains config, state, and the
verification result; project code and criteria remain in the ordinary project files.

## 3. Record the decision, repair, and verify

The failure supports a small repair without changing the Goal:

```sh
agent-loop-harness goal-review --decision continue --evidence "Fractional mean test failed; replace integer division and keep the Goal."
```

Open `average.py`. Change `return sum(values) // len(values)` to `return sum(values) / len(values)`.
Keep the empty-input check and the tests unchanged. Then:

```sh
agent-loop-harness verify
agent-loop-harness status
```

Both tests should pass, `verify` exits **0**, and the recorded phase is `verified`. The new artifact contains
the two executed tests. This verifies the task; it does not automatically close the whole project or choose
a successor. In everyday use, the worker/reviewer follows the project's planning and CLOSE policies.

Changing project files after verification invalidates the evidence when the completion gate next checks it.
`status` reports stored state; it is not itself a fresh completion-gate check. The automated install smoke
also exercises stale-evidence rejection and reverification.

## 4. Continue with your own project

Read [Usage](usage.md) to install the Windows Cursor adapter and initialize your own reviewed plan.
The CLI alone does not start an agent session or enforce a host's stop behavior.

The demo is disposable and has no global hooks. Uninstall the CLI with `python -m pip uninstall agent-loop`.
If you also installed the Cursor adapter, follow the separate uninstall instructions in Usage.

## Maintainer check

From the agent-loop repository, with a build environment active:

```sh
python -m pip install build virtualenv
python scripts/smoke-install.py
```

This builds an sdist and wheel in a temporary directory, installs the wheel into a fresh environment, checks
imports outside the checkout, runs failure → Goal Review → repair → success → stale evidence → reverification,
and uninstalls the package. Build dependencies may use the network. It does not call a model or install host hooks.
