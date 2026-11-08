# Sprint 3

**Dates:** 9 Nov to 22 Nov 2026  ·  **Demo:** ~23 Nov 2026 (to confirm in class 9 Nov)  ·  **Milestone:** [Sprint 3](https://github.com/cacheshift-project/cacheshift/milestone/4)

## Goal
A real run through the gateway, with the semantic cache inside it, prints the one-page report: how often the cache served a wrong answer, and how much it changed how often the expensive model is used. This turns the separate Sprint 2 experiments into one tool a builder can run on their own traffic.

## Committed stories
| Issue | Owner | Acceptance criteria | Done? |
|---|---|---|---|
| #47 Semantic cache inside the gateway | Spencer | Gateway runs with an exact or semantic cache (setting configurable, default 0.90); each request logs its similarity and the matched saved question; replaying the ARC stream reproduces Story 2's wrong-question rates at 0.90 and 0.80; tests pass | ☐ |
| #48 One-page report from a gateway run | Anthony | One command turns a run log into the report from the [Sprint 2 mock-up](../Sprint_2/Report_Mockup.html): cost, cache hit rate, wrong-answer rate, planned vs actual expensive-model share, each rate with a 95% range; tests pass | ☐ |
| #5 Story 3: re-tuning rule | Both | Decided in class 9 Nov, **before** any new run: re-tuning must never cost more than 1 accuracy point, or the report shows the trade-off and the user picks. Story 3's acceptance criteria reworded to match | ☐ |
| #49 Re-tuning step in the report | Anthony | The report shows expensive-model share and accuracy before and after re-tuning, following the #5 decision | ☐ |
| #50 Sprint 3 demo run and report | Both | A question stream runs through the live gateway with the semantic cache and prints the report end to end; this file filled in | ☐ |

**Backlog:** #14 (user conversations; not blocking the build), #3 (full drift report), #7 and #13 (reworded test set, which would measure the semantic cache's savings side; planned for Sprint 4).

## Demo
<!-- What we showed, what actually worked live, what we faked. -->

## Retro
- **What worked:**
- **What broke:**
- **What we're changing next sprint:**

## Assumptions tested this sprint
| Assumption | Test | Result | Pivot? |
|---|---|---|---|
| The semantic cache behaves the same inside the gateway as in the offline Story 2 run | #47: replay the ARC stream at 0.90 and 0.80 and compare wrong-question rates | | |

## LLM chat links used this sprint
<!-- Required in every report. -->
