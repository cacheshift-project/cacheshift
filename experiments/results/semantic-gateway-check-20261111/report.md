# Semantic cache in the gateway vs Story 2 (#47)

970 requests (485 test questions plus uniform repeats, seed 601). Pass = every request gets the same hit/miss decision and matched question in the gateway as in Story 2's offline replay.

| Setting | Hits | Answer served to a different question | Story 2 published (970 questions) | Mismatches | Pass |
|---|---:|---:|---:|---:|---|
| cos>=0.90 | 486 (50.1%) | 1 (0.1%) | 0.4% [0.1, 0.7] | 0 | yes |
| cos>=0.80 | 495 (51.0%) | 22 (2.3%) | 3.2% [2.0, 4.6] | 0 | yes |

The gateway serves only the holdout's test split, so its rates are expected to be close to Story 2's, not identical. The request-by-request match is the pass/fail check.
