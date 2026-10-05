# Sprint 1 — AI review of the plan

The course asks two *different* AI models (not two chats with the same one) to review the Sprint 1 plan and argue about it. The AIs advise; the team decides.

**Models used:** Claude Opus 5.5 (claude.ai, run by Spencer) · ChatGPT (round 1 in Codex, round 2 on chatgpt.com, run by Anthony)
**Plan reviewed:** [`SPRINT1.md` at 4835a60](https://github.com/cacheshift-project/cacheshift/blob/4835a60c258543cb6a132bc59b55ab4cfa459ca8/SPRINT1.md). Both models received this same version and the same three questions.

## Step 1 — same plan, same three questions, to both models

1. What is our riskiest unstated assumption?
2. Why might this fail by week 6?
3. What is missing from our evaluation?

| Question | Claude's answer (summary) | ChatGPT's answer (summary) |
|---|---|---|
| Riskiest unstated assumption | That our synthetic repeats behave like real traffic. RouterBench has no natural repeats, so every cache hit comes from repeats we inject. If repeats are drawn uniformly, drift is zero by construction; any drift we find reflects how we chose to repeat questions. False hits would come from near-twin benchmark items, not real app traffic. | That planned strong-model share is both a stable no-cache baseline and an adequate proxy for a dollar budget. A tuning percentile does not guarantee the same share on test data, and token lengths can change cost at a fixed share. Section 8 assumes the no-cache share equals the plan. |
| Why it might fail by week 6 | The pain may not exist: with a fixed cutoff a cache only removes calls, so spend can only fall. The fix may be a one-line recalibration. The pivot line is too easy to pass and no user is named. Nothing in §4 was proven yet. Story 5 gates stories 1–3 but is not scheduled first; A3 has no test this sprint. | Integrating semantic caching, rewordings, APIs and energy before defining a valid paired experiment. Recorded answers do not show how fresh models handle paraphrases; if A3 fails, the paid-call budget may not cover the sweep. Stage it: originals plus exact repeats first, semantic and live results later. |
| Missing from our evaluation | Baselines: exact-match cache, random removal of the same number of questions, plain recalibration on observed traffic, no-cache at matched spend. Three separate shares (planned, no-cache, cached). Total dollars per 1,000 incoming questions, hit rate, a pre-stated minimum drift. Power: 45 cells may each need many routed questions; bootstrap question groups. Multiple-choice false hits are right by chance about 25% of the time. | Explicit share denominators; measured no-cache calibration error; paired cache-on/off and retuned/untuned comparisons; question-group bootstrap; achievable targets under tied scores; a frozen tuning protocol; a quality non-inferiority margin (being inside the baseline accuracy CI does not prove equal quality). |

Chat links: [Claude (rounds 1 and 2)](https://claude.ai/share/1a046ff9-6cb9-41ad-8612-4ea083ce692d) · ChatGPT round 1 ran in Codex, a local session with no share link; its full text is reproduced at the start of the public round-2 chat: [ChatGPT round 2](___)

## Step 2 — cross the reviews

- **Claude on ChatGPT's critique:** Agreed on the facts (no-cache share ≠ plan; token length can move cost at a fixed share, which Claude had missed) but said neither is the *riskiest*, since reporting dollars and three shares fixes both. Called staging (exact repeats first) ChatGPT's best idea, and adopted the non-inferiority margin and paired comparisons (pairing makes its ~1,000-per-cell estimate an upper bound). Called tied scores minor. Said ChatGPT missed the user (A1), the one-line-fix risk, and key baselines (plain recalibration, matched spend, random removal). Kept its first change, extended: record prompt length in the real-log test, use the observed repeat pattern to drive the exact-repeat stage, add rewordings and live calls last.
- **ChatGPT on Claude's critique:** Agreed we need real-traffic evidence, that the user test is too easy to pass, that recalibration must be a baseline, that the extra baselines are needed, and that planned and no-cache shares must be separated. Largely agreed that with fixed routing a cache cannot raise the model bill. Called three claims too absolute: "zero drift by construction" (finite samples, and the no-cache stream counts repeats while the cache-miss stream counts each question once), "production calibration has no drift" (traffic and cache state change over time), and "false hits are only benchmark artifacts". Corrected the sample-size figure (±3 points for one proportion is not a paired power calculation). Warned that LMSYS-Chat-1M is a gated conversation dataset, not a production cache trace. Would **add** the real-traffic test rather than replace the controlled experiment, and separate two claims: the controlled effect, and its practical relevance.

## Step 3 — what we take from it

**Where they agreed** (probably a real problem):
- Planned share and no-cache share are not the same. Report three shares (planned, no-cache actual, cache actual) with explicit denominators, and dollars per 1,000 incoming questions separately.
- Comparisons must be paired (cache on vs. off, re-tuned vs. not, same question stream), bootstrapped by question group, with cutoffs frozen on tuning data before testing.
- Missing baselines: random removal of the same number of questions, plain recalibration on observed router traffic, and the no-cache router at matched spend. "Within the no-cache margin of error" needs a stated non-inferiority margin.
- With fixed routing, a cache cannot push spending over budget. The pain to validate is the cost/quality trade-off moving away from where the engineer set it, not overspending.
- Our pivot line is too easy to pass; a polite "I'd use that" proves little.
- We need evidence from real traffic: synthetic repeats can show the mechanism, not how often it matters.

**Where they disagreed** (what we decided, and why):
- *Riskiest assumption.* ChatGPT: share as a stable baseline and budget proxy. Claude: synthetic repeats. **We side with Claude.** Our five-seed run (PR #23: exact cache, random repeats, 300 ARC test questions) found the cache moved the strong-model share by −1.7 to +2.2 points, with every 95% CI including zero. ChatGPT's point is real but fixed by reporting, which we adopt anyway.
- *"Zero drift by construction."* **We side with ChatGPT on the wording:** random repeats give zero drift *in expectation*; finite samples still vary, which is what our run shows.
- *Replace or add the real-traffic test.* **We side with ChatGPT: add it.** The controlled exact-cache experiment already runs and isolates the mechanism; the real-traffic test answers whether the mechanism matters.
- *Tied scores.* ChatGPT listed them; Claude called them minor. **We agree with Claude:** in our run the re-tuned share missed the target by 3.3 points because of tuning/test sampling error, not ties.

**The one change we made to the plan because of this review:**
- **A2 is now tested in two parts (§7).** The controlled exact-cache experiment stays; we add a real-traffic check: score real prompts with natural repeats using the RouteLLM router, and compare router scores and prompt lengths of repeated vs. one-off prompts. First candidate is LMSYS-Chat-1M, after checking its access terms and whether its repeats are usable. If no suitable traffic exists, we limit our claims to the controlled conditions we tested.

We also adopted, because both models raised them: the §8 correction (measure the no-cache share; explicit denominators; paired, frozen evaluation, from PR #23), the extra baselines above, and a stricter pivot line (§7).
