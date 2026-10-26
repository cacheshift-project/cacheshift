# Re-tuning under a size-limited cache: protocol (#37, unblocks #5)

**Status: PROPOSED, not yet agreed.** Proposed on #37 on 26 Oct 2026. Do not run
`python -m cacheshift.lru_drift` on the MMLU pool until Spencer and Anthony have agreed this file
on #37; then change this line to "AGREED <date>" in the same commit as the first run. The run records
this file's SHA-256, so the report shows which protocol text was in force.

## Why a new test

In the controlled study the cache started empty and never evicted, so every question missed exactly
once and the router always saw the same 1,824 unique test questions. The re-tuned share (50.99%) was
fixed by that design, not measured (#29). A **size-limited LRU cache** fixes this: popular questions
stay cached, unpopular ones are evicted and miss again, so which questions reach the router depends on
the traffic.

## Fixed in advance

| Item | Value |
|---|---|
| Pool | `data/mmlu_retune_20261007/questions.jsonl` (1,824 tuning / 1,824 test questions) |
| Router scores | Committed single-question scores in `experiments/results/controlled-drift-20261012/scores-*.json`; no new router runs |
| Streams | As in the controlled study: every unique question once, plus the same number of repeats drawn by the policy (uniform, high-score popularity or low-score popularity, 2:1 weights), shuffled |
| Cache | Exact match, LRU, starts empty; capacity **10%** (182) and **25%** (456) of unique questions |
| Untuned cutoff | Fit on every incoming tuning request (no cache), midgap rule, target 50% strong |
| Re-tuned cutoff | Fit on the tuning requests that miss the LRU cache (repeat misses count each time), same rule |
| Order | Both cutoffs fixed before the test stream is drawn |
| Seeds | 601–605 |
| Intervals | 95% paired percentile bootstrap over question groups, 2,000 resamples, conditional on the cutoffs |

## Arms

- **No shift (decides #5):** the same policy in tuning and test: uniform→uniform, high→high, low→low.
- **Shift (descriptive):** tuned on uniform traffic, tested on high- or low-score popularity. This
  measures what happens when traffic changes after tuning. We expect failures here; they are reported,
  not hidden, and they are the argument for re-tuning periodically.

## Pass rule

A run passes if **both** hold:

1. The re-tuned strong-model share of routed requests is within **47–53%**.
2. The paired 95% CI for **re-tuned minus untuned accuracy** has a lower bound **above −1.0 percentage
   point**.

Why 1.0 point: paired intervals in the controlled study were about ±0.85 points wide on 1,824 test
questions, so a true zero effect passes, while the synthetic low-score loss (−1.75 to −2.08 points) fails.

**#5 passes** if every no-shift run passes (2 capacities × 3 policies × 5 seeds = 30 runs). Every run,
failures included, goes in the report.

## Limits (stated now, before results)

Synthetic repeat policies on previously exposed MMLU development questions, not real traffic (#36 is
the real-traffic check); exact matching only, no semantic cache; historical costs; intervals exclude
uncertainty in fitting the cutoffs.

## Run (after agreement)

```bash
python -m cacheshift.lru_drift --run-dir experiments/results/lru-retune-<date>
```

It takes about a minute on a laptop CPU: no GPU, API key or router download, because the scores are
already committed.
