# Re-tuning under a size-limited cache: protocol (#37, unblocks #5)

**Status: AGREED 26 Oct 2026** by Spencer and Anthony on #37, before any run on the MMLU pool.
Proposed by Anthony; Spencer agreed to the design and changed the accuracy rule to pooled decisions
(below). This file was committed before the first run, and the run records its SHA-256, so the report
shows which protocol text was in force.

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

## Decision rule

#5 is decided per **capacity × no-shift policy**: 2 × 3 = **6 decisions**. A decision passes if **both** hold:

1. In **every one of its 5 seeds**, the re-tuned strong-model share of routed requests is within **47–53%**.
2. The paired 95% CI for **re-tuned minus untuned accuracy, pooled over its 5 seeds**, has a lower bound
   **above −1.0 percentage point**. The seeds' paired traces are combined and the bootstrap resamples
   question groups (a group's requests from all five seeds stay together, since the same test groups
   recur in every seed).

**#5 passes** if all 6 no-shift decisions pass. The 4 shift decisions (2 capacities × 2 shifts) are
reported the same way but are descriptive. All 50 runs are also reported individually, failures included.

Why pooled (Spencer, #37): one run's interval is about ±0.85 points wide, so a run passes only if its
estimate is above about −0.15. Even if re-tuning truly cost nothing, a single run would then fail about
one time in three, and requiring all 30 runs to pass would almost surely fail. Why 1.0 point: a true
zero effect clears it comfortably once pooled, while the synthetic low-score loss in the controlled
study (−1.75 to −2.08 points) would not.

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
