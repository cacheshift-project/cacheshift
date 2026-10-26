# Sprint 2

**Dates:** 13 Oct to 1 Nov 2026 *(start date to confirm)*  ·  **Demo:** ___ *(fill in)*

*Draft, 26 Oct: the plan and progress so far. Demo, retro and final results are filled in at the end of the sprint.*

## Goal
Test the two assumptions that decide whether CacheShift matters, A1 (people who build small-budget AI features want this report) and A2 in real traffic (repeated prompts differ from one-off prompts enough to shift the router), and settle the re-tuning quality rule and GPU energy feasibility (A6).

## Committed stories
Milestone [Sprint 2](https://github.com/cacheshift-project/cacheshift/milestone/2). ☑ done · ◐ partly · ☐ not done.

| Issue | Owner | Acceptance criteria | Done? |
|---|---|---|---|
| #36 Real-traffic drift check (A2, part 2) | Spencer | LMSYS-Chat-1M sample with a sampling rule fixed before scoring; router scores of repeated vs one-off prompts with 95% CIs; write-up on whether the skew can move the strong-model share by ≥ 5 points | ☐ |
| #14 Name the target user (A1) | Anthony + Spencer | Three conversations with notes in `docs/sprints/Sprint_1/`; one person named in SPRINT1.md | ◐ User redefined after review as the builder of a small-budget AI feature (freelancer, solo developer, startup's technical person), with the owner as payer and students secondary; interview guide written (PR #34); no conversation yet |
| #38 Report mock-up | Anthony | One page; bill, cached-answer errors and drift with ranges; cost and quality separate; linked from the interview guide | ◐ [`Report_Mockup.html`](Report_Mockup.html) in PR #34 |
| #37 Re-tuning quality margin and drift test | Anthony + Spencer | Margin and a drift scenario where the miss mix moves, agreed and recorded before any results | ☑ Agreed 26 Oct with Spencer's pooled rule ([protocol](LRU_Retune_Protocol.md), committed before the run); PR #41 |
| #5 Story 3: re-tune command | Anthony | All 6 no-shift decisions (capacity × policy) pass: every seed's re-tuned share within 47–53%, and the seed-pooled paired accuracy CI lower bound above −1.0 point | ◐ **5 of 6 pass** ([results](LRU_Retune_Results.md), PR #41). Every share is in range; low-score popularity with a 25% cache costs −0.86 points [−1.38, −0.37]. Open: the team decides how to treat the accuracy cost |
| #35 SCC GPU energy check (A6) | Anthony | NVML energy idle and under load; Llama-3.1-8B full precision and 4-bit with J/token and tokens/s; notes so it can be rerun | ◐ Done on the SCC (PR #40): L40S, 6.28 J/token full precision vs 3.59 J/token 4-bit; closes when PR #40 merges with the JSON report |
| #9 API key works | Anthony + Spencer | One real call on each laptop | ◐ Anthony's call passed with Anthropic `claude-haiku-5-5` (PR #33); Spencer's run pending |
| #39 This report | Anthony | Plan, demo, retro, assumptions and LLM links filled in | ◐ Draft |

**Done early in the sprint:** #29 (controlled-drift report corrections, PR #32) and the Anthropic option in the API check (PR #33). #3, #7 and #13 were moved to the Backlog milestone (Spencer, 26 Oct): the full drift report waits for the real-traffic result, and the rewording work waits for the reworded test set and API budget.

## Demo
- **What we show:** *(fill in; candidates: the report mock-up, SCC energy numbers for Llama full vs 4-bit, the LRU re-tuning result, and the real-traffic skew from #36)*
- **What worked live:** *(fill in after presenting)*
- **What is not real yet:** *(fill in)*

## Retro
- **What worked:** *(fill in)*
- **What broke:** *(fill in)*
- **What we're changing next sprint:** *(fill in)*

## Assumptions tested this sprint
| Assumption | Test | Result | Pivot? |
|---|---|---|---|
| A1: people who build small-budget AI features would use a drift and cached-answer-quality report | Three 15-minute conversations around the mock-up (SPRINT1.md §7); passes if at least one agrees to try it on their own traffic | *(pending)* | *(pending; the pivot line applies if none does)* |
| A2 (real traffic): repeated prompts score differently from one-off prompts | #36 on LMSYS-Chat-1M | *(pending)* | *(pending)* |
| A6: we can read GPU energy on the SCC and run a 4-bit model there | #35: NVML idle reading, then Llama-3.1-8B full and 4-bit | **Holds.** NVML energy works on an SCC L40S (33.5 W idle). Llama-3.1-8B: 6.28 J/token at 41.5 tok/s (bf16) vs 3.59 J/token at 59.0 tok/s (4-bit), batch size 1, one run | No |

## LLM chat links used this sprint
- Claude Code session (Anthony; #29, #9, #14, #35, #37, #38, this report): https://claude.ai/code/session_016kQAwqT5pRuqKDEzzan91j *(check that the link is shared before submitting)*
- *(Spencer: add yours)*
