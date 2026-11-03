# Re-tuning under a size-limited cache: results (#37, #5)

*26 Oct 2026 · protocol [`LRU_Retune_Protocol.md`](LRU_Retune_Protocol.md), agreed on #37 and committed
(3ae87ec) before this run · report [`experiments/results/lru-retune-20261026/report.json`](../../../experiments/results/lru-retune-20261026/report.json)
(protocol SHA-256 `a3576fc3…`; raw traces ignored, their hashes in the report) · 50 runs, 81 s on a laptop CPU*

## Verdict

**#5 does not pass under the agreed rule: 5 of 6 decisions pass.** The one that fails is
low-score popularity with the larger cache (25%). Re-tuning brought its share back on target in every
seed, but the pooled accuracy cost was **−0.86 points [−1.38, −0.37]**, and the lower bound is below the
agreed −1.0. With the smaller cache the same policy passes (−0.36 [−0.64, −0.13]).

| Capacity | Policy (tune → test) | Hit rate | Untuned share | Re-tuned share | Pooled accuracy change, re-tuned − untuned | Decision |
|---|---|---:|---:|---:|---:|---|
| 10% (182) | uniform → uniform | 6.5–8.4% | 50.2–51.5% | 50.2–51.7% | 0.00 [0.00, 0.00] | Pass |
| 10% | high → high | 7.2–7.9% | 48.5–49.7% | 49.6–52.4% | +0.14 [−0.08, +0.36] | Pass |
| 10% | low → low | 7.0–8.0% | 50.3–52.8% | 49.7–51.5% | −0.36 [−0.64, −0.13] | Pass |
| 25% (456) | uniform → uniform | 16.9–18.3% | 49.8–51.1% | 50.1–51.3% | +0.04 [−0.01, +0.13] | Pass |
| 25% | high → high | 16.5–18.5% | 47.2–48.4% | 50.6–52.5% | +0.39 [−0.02, +0.83] | Pass |
| 25% | low → low | 16.5–18.8% | 52.1–53.9% | 49.4–51.5% | **−0.86 [−1.38, −0.37]** | **Fail** |

Shares are the strong model's share of routed requests (ranges across seeds 601–605); the target is 50%.
Accuracy changes are percentage points, pooled over the five seeds, with paired 95% intervals.

## What it shows

1. **The test now does what #29 asked for.** With an LRU cache the miss mix depends on traffic, and the
   re-tuned share is no longer fixed by design: it varies from 49.4% to 52.5% across runs, and every
   no-shift run lands inside 47–53%.
2. **Cache drift is real but small at these hit rates.** The cache moved the strong-model share by about
   ±1 point at 10% capacity and about ±2 points at 25% (paired cache effect −2.4 to −2.1 points for
   high-score popularity, +1.9 to +2.5 for low-score popularity). The controlled study's ±7 points came
   from a cache that never forgot anything. Real hit rates will decide which regime matters (#36).
3. **Restoring the budget costs accuracy when the cache absorbs easy questions.** When easy questions are
   popular, the cache answers them, the router sees harder ones and calls the strong model more. Bringing
   the share back to 50% means fewer strong calls on hard questions, so accuracy drops. This is the same
   direction as the controlled study, and it grows with the drift. With high-score popularity the
   opposite happens and accuracy improves slightly. Re-tuning is a budget-versus-quality trade-off, not
   a free fix.
4. **A traffic change after tuning matters more than the cache** (shift arms, descriptive). Tuned on
   uniform traffic and tested on skewed traffic, the strong-model share moved to 58.8–59.7% (high-score
   popularity) or 41.9–43.2% (low-score popularity) *with no cache at all*, and the caches added only
   about ±1–3 points on top. Re-tuning on the old traffic
   cannot fix that; only re-tuning on the new traffic can. This is the case for re-tuning periodically.

## Limits

Synthetic, score-conditioned repeat policies on previously exposed MMLU development questions, not real
traffic; exact matching only; historical costs; one pool reused across seeds; intervals are conditional on
the fitted cutoffs. The per-run accuracy checks in the report are descriptive only (see the protocol).

## For the team to decide (not decided here)

#5 stays open. Options, for discussion on #5:

- **Keep the rule and report the failure.** Story 3 is met for 5 of 6 settings, and the failing case
  shows a measurable cost.
- **Treat re-tuning as an option the user chooses, with its quality cost shown**, as the report mock-up
  already does ("−0.5 points, likely between −1.1 and 0.0"). Story 3's acceptance would then need
  rewording before any new run. It must not be changed to fit this result.
