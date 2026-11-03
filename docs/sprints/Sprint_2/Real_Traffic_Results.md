# Real-traffic drift check: results (#36, assumption A2 part 2)

*28 Oct 2026 · plan [`Real_Traffic_Plan.md`](Real_Traffic_Plan.md), committed (b6be836) and amended (9d89fb1)
before any prompt was scored · report [`experiments/results/real-traffic-20261028/report.json`](../../../experiments/results/real-traffic-20261028/report.json)
(plan SHA-256 `9469a086…`, matches the committed plan; per-prompt scores ignored, data file hashes in the report) ·
80,620 prompts scored one at a time in about 67 min on a laptop CPU*

## Verdict

**Drift is too small to matter at this traffic's repeat rate: A2 (real traffic) fails under the
pre-set rule.** With a cache that never forgets, the strong model's share of routed requests rises by
**+2.2 points [+0.3, +4.1]**, entirely inside the ±5-point line. Per SPRINT1.md §7, CacheShift continues
as a measurement study and says so.

The effect is real (the interval excludes zero) and goes the direction the controlled study (#28)
predicts, but it is about a third of the ~7 points seen there.

| Measure | Result |
|---|---|
| English requests (first user message) | 777,453 (22.3% of conversations were not English) |
| Unique prompts / repeated prompts | 478,507 / 114,649 |
| Repeat rate (requests that repeat an earlier prompt) | 38.5% |
| Mean router score, repeated − one-off | −0.0012 [−0.0016, −0.0008] |
| Share above the cutoff, repeated − one-off | −1.8 points [−2.6, −0.9] |
| **Drift, never-evicting exact cache** | **+2.2 points [+0.3, +4.1]** |
| Drift, LRU cache holding 10% of unique prompts (hit rate ≈ 16.6%) | +1.7 in all five stream orders |
| Drift, LRU cache holding 25% (hit rate ≈ 25.6%) | +2.0 in all five stream orders |

Cutoff 0.4618 (weighted midgap), giving exactly 50.0% strong with no cache. Intervals are 95% stratified
bootstrap, 2,000 resamples, conditional on the cutoff.

## What it shows

1. **People repeat slightly easier prompts.** Repeated prompts score a little lower than one-off ones,
   so a cache absorbs easy requests and the router sees a harder mix. This is the controlled study's
   mechanism, now seen in real traffic, and the sign is the same in every sensitivity check.
2. **The size is small because the scores barely differ.** The router's scores on this traffic sit in
   a narrow band around the cutoff (means 0.466 vs 0.468). A 38% repeat rate cannot turn a gap that
   small into a large drift.
3. **A size-limited cache gets most of the way there.** An LRU cache holding 10% of prompts already
   produces +1.7 of the +2.2 points, because the most repeated prompts stay in the cache. Stream order
   barely matters (all five orders agree to 0.1 point).
4. **About half the drift comes from a few prompts.** Leaving out the 63 prompts repeated more than 100
   times (possible automated traffic) halves the drift to +1.1 [+0.8, +1.3]. A deployment's drift will
   depend heavily on whether it has a handful of very popular requests.
5. **In practice:** +2.2 points means about 4% more strong-model calls among requests that reach the
   router. That is a budget surprise, not a broken router, and well within what periodic re-tuning (#37)
   can absorb.

## Sensitivity checks (not used for the decision)

| Check | Drift | Would the rule say |
|---|---|---|
| Without prompts containing `NAME_n` placeholders | +2.4 [−0.1, +5.1] | Inconclusive |
| Size-2 groups counted as one request (possible Arena pairs) | +2.3 [+0.3, +4.5] | Too small |
| Without prompts repeated > 100 times | +1.1 [+0.8, +1.3] | Too small |

The name-placeholder check is the only one whose interval reaches the 5-point line, by 0.1 point; it
drops a fifth of the prompts, which widens the interval. The point estimate barely moves (+2.4 vs +2.2).
2,614 scored prompts (about 3.0% of requests) were longer than the router's 512-token limit and were
truncated, as a deployed router would truncate them.

## Limits

As stated in the plan before the run: LMSYS-Chat-1M is traffic to a public research chat site, not a
small-business app; exact-match repeats only (the Story 2 semantic cache would find more); no real
timing, so LRU results assume a random order; router scores only, not answer quality; intervals exclude
uncertainty in fitting the cutoff.

## What this means for the project (for the team to decide)

- **The headline claim changes.** "Caching breaks routing budgets" is not supported on general chat
  traffic. "Caching shifts routing by a measurable amount that depends on the app's traffic, and here is
  how to measure yours" is. That is the measurement-study framing SPRINT1.md §7 already allows for.
- **Where drift could still matter:** apps with higher repeat rates and more lopsided repeats than public
  chat, such as an FAQ bot. The controlled study (±7 points) shows the ceiling; whether real small-business
  traffic gets near it is a question for the target-user conversations (#14), not for this dataset.
- **Story 2 (cached-answer quality) is unaffected** and becomes the stronger half of the report.
