# Example Goal

Plan Revision: 1
Plan Review: approved

## Goal

Fix the arithmetic mean without changing the empty-input contract.

## Current conclusion

The example uses integer division, so the fractional-mean test should fail.
This fixture is pre-approved for the walkthrough; review your own project plans before execution.

## Next decision

Run the tests, inspect the failure, fix the implementation, and verify again.

## t1 Fix fractional means

`average.py` uses integer division. Switch it to true division; `test_average.py` pins the fractional mean and
the empty-input error. Acceptance: both tests pass and the evidence is fresh.

## Experiment Log

| Exp | Hypothesis | Status | Evidence | Conclusion |
|---|---|---|---|---|
| 1 | True division preserves fractional means and rejects empty input | Pending | test_average.py | — |

