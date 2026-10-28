# Real-traffic drift check: plan (#36, assumption A2 part 2)

**Status: FIXED 28 Oct 2026, before any LMSYS prompt was scored.** This file is committed before the
first scoring run. The run records this file's SHA-256, so the report shows which plan was in force.
Any later change is a new dated section below, never an edit of these rules.

## Why this test

The controlled study (#28) showed the mechanism: when the repeated questions lean easy or hard, a
cache shifts the router's strong-model share by about 7 points; with random repeats it does not. Whether
that matters depends on real traffic: **are the prompts people repeat easier or harder (by router score)
than the ones they ask once?** This check answers that on LMSYS-Chat-1M and turns it into the drift a cache
would cause at that traffic's own repeat rate.

## Fixed in advance

| Item | Value |
|---|---|
| Data | `lmsys/lmsys-chat-1m` on Hugging Face (dataset revision recorded in the report). Raw files stay in `data/raw/` (git-ignored) and are never committed; the license forbids redistribution |
| Prompt | The first `user` message of each conversation; one conversation = one request |
| Language | `language == "English"` only (the router was trained on English chat). The non-English share is reported |
| Repeat key | Text with leading/trailing whitespace removed and every run of whitespace collapsed to one space. Case-sensitive. Empty keys are dropped |
| Groups | All requests with the same key form one prompt group. **Repeated:** group size ≥ 2. **One-off:** size 1 |
| Scored set | Every repeated key (if more than 30,000, a random 30,000 with seed 601), plus a random 20,000 one-off keys (seed 601). Each scored key carries a weight of (keys in its stratum) / (keys scored in its stratum) |
| Router | `routellm/bert` at the pinned revision in `cacheshift/router.py`, CPU, scored **one prompt at a time** (batch size 1, as in the controlled study's single-score audit), on the normalized key. Input length and truncation at 512 tokens recorded |
| Cutoff | Weighted midgap rule (same rule as `calibrate_midgap`): 50% of all requests go to the strong model with no cache |
| Seeds | 601 for sampling and the bootstrap; 601–605 for LRU stream orders |
| Intervals | 95% percentile bootstrap, 2,000 resamples of prompt groups within each stratum, conditional on the fitted cutoff (as in Sprint 1) |

## What is measured

1. **Repeat rate:** share of requests that are repeats (requests minus unique keys, over requests), and the
   number of repeated groups.
2. **Score gap (the mechanism):** mean router score of repeated keys minus one-off keys, and the
   difference in share above the cutoff, each with a 95% CI. Each key counts once here.
3. **Drift, never-evicting exact cache (headline):** with the cache on, each unique key reaches the router
   once. Drift = strong-model share of routed requests with the cache on minus with it off (50% by
   construction), in percentage points. This is the largest drift an exact cache can cause on this
   traffic, so it is an upper bound.
4. **Drift, size-limited LRU cache (secondary):** the same drift for an LRU exact cache holding 10% and 25%
   of the unique keys (`lru_misses` from #37), replaying the English requests in five random orders
   (seeds 601–605; LMSYS has no usable timestamps). Reported as each order's value and the range.

## Decision rule (on measure 3)

| 95% CI for drift | Conclusion |
|---|---|
| Entirely beyond ±5 points | **Drift matters in real traffic.** A2 holds |
| Entirely inside ±5 points | **Drift is too small to matter at this traffic's repeat rate.** A2 (real traffic) fails; per SPRINT1.md §7 we continue as a measurement study and say so |
| Anything else | **Inconclusive** |

The 5-point line is the threshold already set in #36. The score gap (measure 2) is reported either way; it
says which direction drift would go at higher repeat rates, such as an FAQ-style chatbot.

## Sensitivity checks (reported, not used for the decision)

- Measures 2 and 3 again without keys containing LMSYS's name placeholders (`NAME_1`, `NAME_2`, ...), since
  redaction can make different prompts identical.
- Number and share of scored prompts truncated at 512 tokens (kept in all analyses; a deployed router
  truncates them the same way).

## What gets committed

`experiments/results/real-traffic-<date>/report.json` and `report.md`: counts, rates, scores summaries,
cutoff, drifts and intervals only. **No LMSYS text, not even examples.** Per-prompt scores go to
`experiments/results/real-traffic-<date>/raw/` (git-ignored).

## Limits (stated now, before results)

- LMSYS-Chat-1M is traffic to a public research chat site, not a business app; its repeat rate and topics
  may differ from a small-business chatbot.
- Exact-match repeats only; the semantic cache from Story 2 would find more.
- Requests are treated as one stream without real timing, so LRU results depend on the assumed random order.
- The router's scores on this traffic are not checked against answer quality; this measures where requests
  would be sent, not whether answers are correct.
- Intervals exclude uncertainty in fitting the cutoff.
