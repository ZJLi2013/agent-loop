# Example Goal

Plan Revision: 1
Plan Review: approved

## Goal

Fix the arithmetic mean without changing the empty-input contract.

## Design

Switch `average` from integer to true division and keep the empty-input error. Sample output: `average([1, 2])`
returns `1.5`. Not done: no change to the tests or the empty-input check. Acceptance: both tests in
`test_average.py` pass under the locked verifier and the evidence is fresh.

## Current conclusion

The example uses integer division, so the fractional-mean test should fail.
This fixture is pre-approved for the walkthrough; review your own project plans before execution.

## Thread

| Stage | Question | Conclusion | What it changed |
|---|---|---|---|
| fractional-mean | Does true division fix fractional means? | Pending | Run the tests, inspect the failure, fix, verify again |

---
Execution details below; the human need not read them.

## fractional-mean Fix fractional means

`average.py` uses integer division. Switch it to true division; `test_average.py` pins the fractional mean and
the empty-input error. Acceptance: both tests pass and the evidence is fresh.

## Experiment Log

| Exp | Hypothesis | Status | Evidence | Conclusion |
|---|---|---|---|---|
| 1 | True division preserves fractional means and rejects empty input | Pending | test_average.py | — |
