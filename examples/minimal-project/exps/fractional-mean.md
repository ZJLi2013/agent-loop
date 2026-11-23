# The mean still truncates fractions

- **目标**: `average([1, 2])` returns `1.5` and empty input still raises.
- **现状**: integer division; the fractional-mean test fails.
- **下一步**: switch to true division and rerun the locked verifier.

## Experiment Log

| Exp | Hypothesis | Status | Evidence | Conclusion |
|---|---|---|---|---|
| 1 | True division preserves fractional means and rejects empty input | Pending | test_average.py | — |
