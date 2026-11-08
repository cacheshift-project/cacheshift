# Sprint 2

**Dates:** 13 Oct to 1 Nov 2026  ·  **Demo:** 4 Nov 2026 (in-class presentation) · **Slides:** [Sprint2_Presentation.pdf](Sprint2_Presentation.pdf)

## Goal
Test whether the cache's effect on routing matters in real traffic (A2, part 2), show that cached answers can be checked (Story 2), settle the re-tuning quality rule (#37/#5), confirm GPU energy can be measured (A6), and pin down the target user (A1).

## Committed stories
Milestone [Sprint 2](https://github.com/cacheshift-project/cacheshift/milestone/2). ☑ done · ◐ partly · ☐ not done.

| Issue | Owner | Acceptance criteria | Done? |
|---|---|---|---|
| #36 Real-traffic drift check (A2, part 2) | Spencer | Sampling plan fixed before scoring; router scores of repeated vs one-off prompts with 95% CIs; is the drift ≥ 5 points? | ☑ PRs #43, #44. 777,453 English LMSYS-Chat-1M requests: drift **+2.2 points [+0.3, +4.1]**, inside the ±5-point line, so **A2 (real traffic) fails as planned** ([results](Real_Traffic_Results.md)) |
| #4 Story 2: what a cached answer costs in quality | Spencer | False hits and inherited errors per cache setting with 95% CIs; hand check of 50 agrees ≥ 90% | ☑ PR #31. Semantic cache built; at cos ≥ 0.90, 0.4% of answers go to a different question (−0.3 accuracy points); at ≥ 0.80, 3.2% (−2.5 points). Blind hand check 48/50 (96%) ([write-up](Story2_Cache_Quality.md)) |
| #37 Re-tuning quality margin and drift test | Anthony + Spencer | Margin and a drift test where the miss mix moves, agreed before any results | ☑ PR #41. Size-limited (LRU) cache test; Spencer's pooled rule; protocol committed before the run ([protocol](LRU_Retune_Protocol.md)) |
| #5 Story 3: re-tune command | Anthony | All 6 no-shift decisions pass: every seed's re-tuned share within 47–53%, and the seed-pooled paired accuracy CI lower bound above −1.0 point | ◐ **5 of 6 pass** (PR #41, [results](LRU_Retune_Results.md)). Every re-tuned share lands in 47–53%. Easy questions popular with a 25% cache costs **−0.86 points [−1.38, −0.37]**, so that setting fails. How to treat the cost is decided in Sprint 3 |
| #35 SCC GPU energy check (A6) | Anthony | NVML energy idle and under load; Llama-3.1-8B full and 4-bit with J/token and tokens/s; rerunnable notes | ☑ PR #40. NVIDIA L40S, one run: **6.28 J/token at 41.5 tok/s (bf16) vs 3.59 J/token at 59.0 tok/s (4-bit)**, 43% less energy and 42% faster; 33.5 W idle ([notes](SCC_Energy_Check.md)) |
| #14 Name the target user (A1) | Anthony + Spencer | Three conversations with notes; one person named in SPRINT1.md | ◐ User narrowed (PR #34) to **the builder of a small-budget AI feature** (freelancer, solo developer, startup's technical person); owner as payer, students secondary. Interview guide and candidate list written. **No conversations held**, so A1 is untested; carried to Sprint 3 |
| #38 Report mock-up for interviews | Anthony | One page; cost and quality separate; ranges on every number; linked from the guide | ☑ PR #34 ([mock-up](Report_Mockup.html)) |
| #9 API key works | Anthony + Spencer | One real call on each laptop | ☑ PRs #33 (Anthony, Anthropic `claude-haiku-5-5`) and #42 (Spencer) |
| #29 Controlled-drift report fixes | Anthony | Report commit named; empty-cache guarantee explained; 1.6447 → 1.64 | ☑ PR #32 |
| Demo and slide figures | Spencer | Semantic-cache demo and figures generated from committed reports | ☑ PR #45 |
| #39 This report | Anthony | Plan, demo, retro, assumptions, LLM links | ☑ This file |

**Moved to Backlog (26 Oct):** #3 (full drift report), #7 (reworded test set), #13 (rewording check). They wait on the real-traffic result and the API budget.

## Demo
- **What we show:** a semantic cache in front of a made-up bakery chatbot (`python -m cacheshift.cache_demo --step`, PR #45). Six prepared questions run at three match settings, ≥ 0.80, ≥ 0.90 and ≥ 0.95 similarity. Loose settings reuse right answers ("When do you open on Saturday?") but also serve wrong ones ("What time do you close on Sunday?" gets Saturday's closing time; "Are your muffins dairy-free?" gets the nut-free answer). At ≥ 0.90 there is one wrong answer; at ≥ 0.95 every question goes to the model. The slides then show the measured versions of this: cached-answer quality by setting, real-traffic drift, the re-tuning trade-off and GPU energy.
- **What worked live:** shown in class as a screenshot of the `--step` run's terminal output, walked through one question at a time; the full script ran without problems in our run-through. The bakery questions, answers and right/wrong key are made up and written by hand; the cache code and the similarity model are the real ones from Story 2.
- **What is not real yet:** the semantic cache runs in offline tests and the demo but is **not wired into the running gateway**. Answers are recorded RouterBench answers (replay mode), not live model calls. The energy numbers are one run on one GPU.

## Retro
- **What worked:**
  - **Fixing the plan before seeing results.** #36's sampling plan and #37's protocol were committed (with SHA-256 in each report) before anything was scored. A2 failing is therefore a clean result, not a judgment call.
  - **Reviewing each other's plans before running them.** Spencer's pooled rule for #37 stopped us from requiring 30 separate passes that would have failed by chance. His review of PR #34 moved the user from the owner to the builder.
  - **The SCC worked first time**, after one fix: on a shared node, the GPU-energy library reads the wrong GPU unless told which one the job was given.
  - **Reusing committed router scores** made the #37 test take 81 seconds, with no GPU and no new scoring.
- **What broke:**
  - **A1 was not tested.** No interviews happened, which was the plan's riskiest assumption and the one item that needed people outside the team.
  - The **Sprint 2 report was late**, and the semantic cache is still not inside the gateway.
  - **Setup friction early on:** GitHub write access for the assistant, and Windows line endings that made every file show as changed.
  - **Two questions in class we answered poorly:** how the similarity score is computed, and how the energy numbers were measured.
- **What we're changing next sprint:**
  - User conversations (#14) move to the Backlog. They are not blocking the Sprint 3 build.
  - Every number in the next presentation gets a one-line "how it was measured" in the speaker notes.
  - The gateway produces the one-page report from a real run, with the semantic cache inside it (Sprint 3 demo goal).
  - Decide in week 1 whether re-tuning must never cost accuracy or shows the user the trade-off, and reword Story 3 **before** any new run.

## What we changed or dropped
- **The headline.** "Caching breaks routing budgets" is not supported by real traffic. We now measure how much the cache shifts routing on a given app's traffic rather than warn that it always breaks.
- **Plain random sampling for #36.** One prompt appeared 10,464 times and a random sample could miss it, so the plan switched to sampling by repeat count. This was amended before anything was scored.
- **Cache in the live gateway:** deferred to Sprint 3.

## Assumptions tested this sprint
| Assumption | Test | Result | Pivot? |
|---|---|---|---|
| A2 (real traffic): repeated prompts differ enough to shift the strong-model share by ≥ 5 points | #36: 777,453 LMSYS-Chat-1M requests, plan fixed before scoring | **Fails.** +2.2 points [+0.3, +4.1]: real, and in the predicted direction (people repeat slightly easier prompts), but small. Half of it comes from 63 prompts asked 100+ times | **Yes, as SPRINT1.md §7 planned.** We continue as a measurement study and say so. Cached-answer quality (Story 2) becomes the stronger half of the report |
| A6: we can read GPU energy on the SCC and run a 4-bit model there | #35: NVML idle reading, then Llama-3.1-8B in full precision and 4-bit | **Holds.** L40S: 33.5 W idle; 6.28 vs 3.59 J/token | No |
| Re-tuning restores the budget without costing quality (Story 3) | #37: LRU cache, 6 pre-agreed decisions | **Mostly.** Share restored in every run; one of six settings costs more than the agreed 1 point | Open: decided in Sprint 3 |
| A1: builders of small-budget AI features would use this report | Three interviews around the [mock-up](Report_Mockup.html) | **Not tested.** No conversations held | Not yet. Moved to the top of Sprint 3; the §7 pivot line still applies |

## LLM chat links used this sprint
- Claude Code session (Anthony; #29, #9, #14, #35, #37, #38, this report): https://claude.ai/code/session_016kQAwqT5pRuqKDEzzan91j *(check that the link is shared before submitting)*
- *(Spencer: add yours)*
