# Sprint 3

**Dates:** 9 Nov to 15 Nov 2026  ·  **Presentation:** week of 16 Nov (the course calls it "Sprint 4"; day to confirm)  ·  **Milestone:** [Sprint 3](https://github.com/cacheshift-project/cacheshift/milestone/4)

## Goal
A real run through the gateway, with the semantic cache inside it, prints the one-page report: how often the cache served a wrong answer, and how much it changed how often the expensive model is used. This turns the separate Sprint 2 experiments into one tool a builder can run on their own traffic. It is the last sprint before the 4 Dec poster session, so its results go on the poster.

## Committed stories
| Issue | Owner | Acceptance criteria | Done? |
|---|---|---|---|
| #47 Semantic cache inside the gateway | Spencer | Gateway runs with an exact or semantic cache (setting configurable, default 0.90); each request logs its similarity and the matched saved question; replaying the ARC stream reproduces Story 2's wrong-question rates at 0.90 and 0.80; tests pass | ☑ PR #53, merged 17 Nov |
| #48 One-page report from a gateway run | Anthony | One command turns a run log into the report from the [Sprint 2 mock-up](../Sprint_2/Report_Mockup.html): cost, cache hit rate, wrong-answer rate, planned vs actual expensive-model share, each rate with a 95% range; tests pass | ☐ PR #52, review fixes in, waiting on approval |
| #5 Story 3: re-tuning rule | Both | Decided in class 9 Nov, **before** any new run: re-tuning must never cost more than 1 accuracy point, or the report shows the trade-off and the user picks. Story 3's acceptance criteria reworded to match | ☑ Option A (show the trade-off), confirmed by Spencer 10 Nov; SPRINT1.md row reworded in PR #54 |
| #49 Re-tuning step in the report (stretch) | Anthony | The report shows expensive-model share and accuracy before and after re-tuning, following the #5 decision | ☐ PR #54 open (stacked on #52) |
| #50 Sprint 3 demo run and report | Both | A question stream runs through the live gateway with the semantic cache and prints the report end to end; this file filled in | ☐ |

**Backlog:** #14 (user conversations; not blocking the build), #3 (full drift report), #7 and #13 (reworded test set, which would measure the semantic cache's savings side; listed as future work on the poster).

## Demo
<!-- What we showed, what actually worked live, what we faked: fill in after presenting. -->

**Demo run** (`python -m cacheshift.sprint3_demo --run-dir experiments/results/sprint3-demo-20261117`, run 17 Nov on a Linux CPU). The 485 ARC holdout test questions plus uniform repeats (970 requests, seed 601) go through the live HTTP gateway three times: with no cache, with the semantic cache at 0.90, and with the semantic cache and a re-tuned cutoff. All answers are recorded answers, so there are no live model calls. Ranges are 95% bootstrap over question groups.

| | Result |
|---|---|
| Cost per 1,000 requests | $0.28 [0.25, 0.30], vs $0.92 if everything went to the expensive model (−70%) |
| Answered from the cache | 50.1% [47.8, 52.2] |
| Saved answer given to a different question | 1 request (0.10% [0.00, 0.32]); it happened to be right, so 0 wrong as a result |
| Wrong answers repeated from the cache | 4.74% (already wrong when first given) |
| Accuracy | 90.0% [87.1, 92.7]; cache vs the same stream with no cache: +0.0 points |
| Expensive-model share of routed requests | 55.2% [50.5, 59.8] vs a 50% plan: +5.2 points, outside ±3 |
| … of which caused by the cache | +0.0 points [−2.3, +2.3]: the drift comes from the cutoff fitted on tuning questions, not from the cache |
| Re-tuning (#49), held-out half (244 groups) | Cutoff 0.4659 → 0.4669; share 56.1% → 55.3% [48.8, 61.9]; accuracy +0.0; cost $0.29 → $0.28 per 1,000. With ~240 routed requests per half, the range is wider than ±3, so this run cannot show re-tuning landing within the band on new questions |

## Retro
- **What worked:**
- **What broke:**
- **What we're changing next sprint:**

## Assumptions tested this sprint
| Assumption | Test | Result | Pivot? |
|---|---|---|---|
| The semantic cache behaves the same inside the gateway as in the offline Story 2 run | #47: replay the ARC stream at 0.90 and 0.80 and compare wrong-question rates | Holds. At 0.90: 0.1% of requests vs Story 2's 0.4% [0.1, 0.7]; at 0.80: 2.3% vs 3.2% [2.0, 4.6]; 0 requests differ from Story 2's replay (PR #53) | No |

## LLM chat links used this sprint
<!-- Required in every report. -->
- Claude (review fixes for #52, re-tuning step #49, demo run): https://claude.ai/code/session_01GioLAAaYAGLNK4RQ84y99o
