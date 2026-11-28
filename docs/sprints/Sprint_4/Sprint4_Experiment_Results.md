# Sprint 4 experiments: results (27 Nov 2026)

There are three tests and one fix, each answering a "next step" from the Sprint 3 slides. The first two followed protocols committed before they ran: [Retune_Scale_Protocol.md](Retune_Scale_Protocol.md) at 18:03 and [Uneven_Repeats_Protocol.md](Uneven_Repeats_Protocol.md) at 18:11. Every outcome is reported, whatever it showed.

**Common setup**
- Data: every RouterBench MMLU question with an official key, 6,875 test and 6,849 tuning questions in 57 subjects.
- Router: RouteLLM's router with its cutoff set on the tuning questions to a 50% plan.
- Cache: the semantic cache at 0.90.
- Answers: recorded answers (GPT-4 expensive, Mixtral cheap).
- Ranges: 95% bootstrap over question groups.

## 1. Re-tuning at scale: **it works**

At 14× the Sprint 3 demo's size, re-tuning lands inside ±3 points on questions it was not fitted to.

| | Expensive-model share | Range |
|---|---|---|
| Original cutoff 0.4548, held-out half | 51.5% | 49.8 to 53.2 |
| **Re-tuned cutoff 0.4552, held-out half** (primary) | **50.2%** | **48.6 to 52.0**, so within ±3 |
| Re-tuned on the other half (reverse check) | 49.4% | 47.6 to 51.1, within |
| Cross-fit: every question judged by a cutoff not fitted to it | 49.8% | 48.6 to 51.0, within |

- **Accuracy cost of re-tuning** (held-out half): −0.15 points [−0.36, +0.04], well above the −1.0 margin from #37. Cost: −$0.008 per 1,000.
- **Before re-tuning**, the original cutoff drifted +1.4 points [+0.2, +2.6] on the full test stream. Of that, +1.3 [+0.6, +1.9] came from the cache itself (paired against the same stream with no cache).
- **Why the Sprint 3 demo couldn't tell:** its held-out half had about 240 routed requests. Here it has 3,236, and the range shrank from ±6.5 to ±1.7 points.

## 2. Uneven repeats: **the budget held**, but the router barely tells easy topics from hard

| Repeat policy | Cut-off | Cache's effect on expensive-model share | Verdict |
|---|---|---|---|
| Easy topics asked 3× (primary) | 0.4551 | +0.3 points [−0.5, +1.1] | within ±3 |
| Hard topics asked 3× | 0.4547 | +1.5 [+0.8, +2.2] | within ±3 |
| Uniform | 0.4550 | +1.3 [+0.6, +2.0] | within ±3 |

- Each cutoff was set on the same policy's no-cache tuning stream, which gave 50.0% on the tuning stream every time.
- **The expected direction did not appear.** The protocol expected a positive effect for easy-repeat and a negative one for hard-repeat. The likely reason is that the router scores the topic levels almost the same: mean router score 0.458 for easy, 0.456 for hard, 0.455 for other. A skew the router cannot see cannot move its budget. So this test shows the budget holds for this skew; it does not rule out the mechanism for a skew the router *does* see. The engineered score skews in #37 (Sprint 1–2) did move it.

## 3. A finding we did not plan: on MMLU, 0.90 is **not** a safe match setting

On ARC, 0.90 caused no wrong answers in the Sprint 3 demo. On MMLU, in the same pipeline:
- **567 of 13,750 requests (4.1% [3.6, 4.7]) got another question's saved answer and were wrong because of it.**
- Accuracy against the same stream with no cache: **−1.7 points [−2.2, −1.3]**.

The 745 wrong-question hits are concentrated in **templated questions**. 456 are "moral scenarios" questions, which all share a long identical lead-in. About 200 are history questions where several *different* questions follow the same long passage, at similarity up to 0.998. The embedding is dominated by the shared text, so the cache matches the template rather than the question.

**For a builder:** if your questions arrive wrapped in a long shared context (a system prompt, a document, a form), a similarity threshold that is safe on short questions is not safe for you. Check wrong answers on your own traffic. That is exactly what the report now leads with (#58).

## 4. Reworded questions: **the cache catches most rewordings** (pending the hand check)

There are 120 MMLU test questions (40 easy, 40 hard, 40 other topics). Each was reworded by Claude with the answer options unchanged ([data](../../../data/reworded_20261127/rewordings.jsonl)). The cache holds all 6,875 test questions, and each rewording is looked up in it.

| Setting | Full prompt (as the gateway stores it): caught | wrong question | Question text only: caught | wrong question |
|---|---|---|---|---|
| 0.95 | 72 / 120 | 0 | 47 / 120 | 0 |
| 0.90 | 111 / 120 | 0 | 82 / 120 | 1 (its answer happened to be right) |
| 0.85 | 118 / 120 | 0 | 106 / 120 | 1 |
| 0.80 | 120 / 120 | 0 | 113 / 120 | 1 |

- An exact-text cache catches 0 of these, so this is the savings side that Sprint 2 could not measure.
- The full prompt repeats the answer options, which inflates similarity. The question-only column is closer to how a chatbot user asks.
- **These numbers count only after the #7 hand check:** a person marks each rewording as keeping its meaning (at least 95% must). The sheet is "CacheShift reworded questions: hand check".
- A rewording the cache misses would need a live model answer, so accuracy on misses is not measured.

## 5. The fix: a difference check **cuts wrong answers from the cache by 88%**

This follows a protocol committed before it ran ([Difference_Check_Protocol.md](Difference_Check_Protocol.md), 20:14). Before reusing a saved answer, the cache trims the words the two prompts share at the start and end. It then reuses the answer only if the parts that differ are at least 0.80 alike. A shared template or passage can no longer carry the match.

| MMLU, same stream as section 1 | Wrong answers caused by the cache | Accuracy vs fresh | Answered from cache | Cost per 1,000 | Expensive-model share |
|---|---|---|---|---|---|
| Cache 0.90, no check (section 3) | 567, 4.12% [3.64, 4.66] | −1.7 [−2.2, −1.3] | 52.8% | $0.33 | 51.4% |
| **Cache 0.90 + check 0.80** (primary) | **67, 0.49% [0.33, 0.66]** | **−0.3 [−0.5, −0.1]** | 50.4% | $0.35 | 49.8% |
| Cache 0.90 + check 0.90 | 27, 0.20% [0.10, 0.32] | −0.1 [−0.2, +0.0] | 50.2% | $0.35 | 49.7% |
| Cache 0.90 + check 0.70 | 248, 1.80% [1.50, 2.12] | −0.5 [−0.8, −0.3] | 51.4% | $0.34 | 50.5% |
| Cache 0.80 + check 0.80 | 169, 1.23% [0.96, 1.50] | −0.7 [−0.9, −0.4] | 50.9% | $0.34 | 49.8% |

- **Primary result: met.** The protocol's bar was an upper range below 1% of requests. The result is 0.66%.
- **What it costs:** 2.4 points fewer answers from the cache, and about $0.015 more per 1,000 questions. As a side effect, the cache's own push on the expensive-model share disappears (49.8% vs the 50% plan).
- **ARC (no regression):** at 0.90 nothing changes: 0 wrong answers, 50.1% from the cache. At 0.80 it helps a little: 20 → 15 wrong answers caused, accuracy −2.0 → −1.5.
- **Rewordings** (pending the hand check): at 0.90 the check lowers catches from 111 to 97 of 120, with no wrong-question matches. At 0.80 it lowers them from 120 to 102, with 3 wrong-question matches. The check gives up some real rewordings to stop template matches.
- **For a builder:** if your questions share long context, turn the check on. If they're short and varied, it changes little.


**The safe setting finder on the same MMLU traffic** (`cacheshift.setting_finder`, limit 0.5%):

| Setting | From cache | Wrong answers caused | Cost per 1,000 |
|---|---|---|---|
| 0.95 | 50.8% | 174 [0.99%, 1.57%] | $0.34 |
| **0.95 + check** (recommended) | 50.2% | **27 [0.10%, 0.31%]** | $0.35 |
| 0.90 | 52.8% | 567 [3.66%, 4.65%] | $0.33 |
| 0.90 + check | 50.4% | 67 [0.33%, 0.67%] | $0.35 |
| 0.85 | 54.5% | 911 [6.00%, 7.32%] | $0.33 |
| 0.85 + check | 50.6% | 115 [0.63%, 1.05%] | $0.34 |
| 0.80 | 55.6% | 1,116 [7.41%, 8.93%] | $0.32 |
| 0.80 + check | 50.9% | 169 [0.97%, 1.51%] | $0.34 |

On MMLU, no setting is safe without the check; with it, 0.95 stays under the limit. On the Sprint 3 ARC traffic the finder recommends 0.95 alone.

## 6. Robustness of re-tuning (added after the first results, not in the protocol)

- **A second stream seed (602) gives the same verdict and almost the same numbers:** 50.2% [48.6, 52.0], and 49.8% for the cross-fit. That's expected. With the cache on, the router sees each question about once, so the order and number of repeats hardly matter.
- **What does vary is which questions fall in the fit half.** The check below was redone over 20 random half-splits (SHA-256 of "salt:group"). Each split's re-tuned run was rebuilt from the logged router scores (`cacheshift.retune_splits`). The rebuild matches the three real re-tuned runs exactly: 0 differences in 41,250 requests.

| Of 20 random splits | Count |
|---|---|
| Within ±3 (estimate and whole range) | **16** |
| Estimate within ±3, range touching the edge | 3 |
| Estimate just outside (53.2% [51.5, 55.0]) | 1 |

- Every re-tuned estimate falls between 49.0% and 53.2%, and every accuracy change between −0.4 and +0.1 points.
- **Plainly:** at about 3,200 routed requests per half, re-tuning brings the share back near plan in most splits but not all. The report's "too few questions to be sure" label is the right thing to show when it doesn't.

## Limits
- MMLU and ARC multiple choice only, recorded answers and one seed.
- The skews are chosen stand-ins for user behaviour, not measured behaviour.
- The router may have seen MMLU-like data in training.

## Reproduce
- `python tools/build_mmlu_retune.py --routerbench data/raw/routerbench_0shot.pkl --download-keys --all-families --output data/mmlu_all_20261127`
- `python -m cacheshift.retune_scale --run-dir …` (about 35 minutes on 2 CPU cores)
- `python -m cacheshift.uneven_repeats --run-dir …` (minutes once router scores are cached in `data/cache/router_scores.jsonl`)
- `python -m cacheshift.reworded_check --out …`
- `python -m cacheshift.difference_check --run-dir … --mmlu-fresh <section 1 run>/no_cache.jsonl.gz`

**Side fix found while running:** the router defaulted to 4 CPU threads. On a 2-core machine that made long prompts about 40× slower (15.3 s vs 0.35 s per question, same scores). It now uses at most as many threads as the machine has cores. This also speeds up the dashboard's start on a small laptop.
