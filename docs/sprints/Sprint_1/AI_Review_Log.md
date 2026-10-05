# Sprint 1 — AI review of the plan

The course asks two *different* AI models (not two chats with the same one) to review the Sprint 1 plan and argue about it. The AIs advise; the team decides.

**Review status (2026-10-05):** ChatGPT/Codex's initial review, the user-supplied Claude critique, and ChatGPT's Round 2 cross-review are recorded. Claude's cross-review, course-accessible chat links, and the final team decision remain pending; issue #15 is not complete.

**Models used:** ChatGPT/Codex in Anthony's current chat; Claude as attributed in Anthony's supplied Round 2 prompt. Claude's exact model/version, original run date and chat link were not supplied. Its text is preserved as supplied, not independently authenticated.
**Plan reviewed:** [`SPRINT1.md` at 4835a60c258543cb6a132bc59b55ab4cfa459ca8](https://github.com/cacheshift-project/cacheshift/blob/4835a60c258543cb6a132bc59b55ab4cfa459ca8/SPRINT1.md), before the evaluation correction merged in PR #23.

## Step 1 — same plan, same three questions, to both models

1. What is our riskiest unstated assumption?
2. Why might this fail by week 6?
3. What is missing from our evaluation?

| Question | Claude's answer (summary) | ChatGPT's answer (summary) |
|---|---|---|
| Riskiest unstated assumption | Synthetic repeats may not represent real traffic, so controlled A2 results cannot establish production prevalence. | That planned strong-model share is both a stable no-cache test baseline and an adequate proxy for a monetary budget. A tuning percentile does not guarantee the same share on test data, and token lengths can change cost even at a fixed share. Section 8 currently assumes the no-cache share equals the plan. |
| Why it might fail by week 6 | The user need and novelty may be weak; the cost-versus-share objective, feasibility evidence, work sequencing and live-model availability need clarification. | The team could spend its time integrating semantic caching, rewordings, APIs and energy measurement before defining a valid paired experiment. Recorded answers do not establish fresh-model behavior on paraphrases; if A3 fails, the paid-call budget and timeline may not support the proposed sweep. Keep an originals-plus-exact-repeats baseline and treat semantic and live results as separate stages. |
| Missing from our evaluation | Add exact-cache, random-removal, ordinary recalibration and matched-spend baselines; distinguish planned and measured shares; specify power, grouping and human-label checks. | Explicit share denominators; measured no-cache test calibration error; paired cache-on/off and retuned/untuned comparisons; question-group bootstrap for dependent repeats; achievable targets under tied scores; a frozen tuning protocol; and a quality non-inferiority margin. Being inside the baseline accuracy CI does not prove equivalent quality. |

Chat links: Claude pending · [ChatGPT/Codex local conversation](codex://threads/01a0cffd-318f-7100-846f-41901b98be6d). This is a local application link, not a public share link; a course-accessible link still needs to be supplied before submission.

## Step 2 — cross the reviews

Give each model the other's critique and ask it to attack or defend it.

- Claude on ChatGPT's critique: pending actual response.
- ChatGPT on Claude's critique: [Round 2 response](Anthony_ChatGPT_Round2_Response.txt), completed 2026-10-05. It agrees on the external-validity, baseline and novelty concerns; qualifies claims of exactly zero drift, guaranteed budget compliance and perfectly stable production calibration; and recommends adding a real-request check alongside the controlled baseline.

Chat links: both cross-review links pending.

## Step 3 — what we take from it

**Where they agreed** (probably a real problem):
- Both supplied initial critiques identify the planned-versus-measured baseline problem, cost/share ambiguity, replay limitations and evaluation design gaps. This is a comparison of their texts, not a claim that Claude has accepted the Round 2 response.

**Where they disagreed** (what we decided, and why):
- Claude recommends replacing A2 with a real-traffic test; ChatGPT recommends retaining the controlled baseline and adding a real-request check. ChatGPT also qualifies the zero-drift and no-future-drift claims. Claude's response to these points and the team's final decision are pending.

**The one change we made to the plan because of this review:**
- Implemented in merged PR #23: Section 8 now corrects the baseline assumption and specifies the denominator, paired comparisons and tuning/test separation. This change came from the first ChatGPT review; it is not represented as a completed two-model consensus.

## Source files and remaining steps

- [Supplied Round 2 prompt](Anthony_ChatGPT_Round2_Prompt.txt) includes both initial critiques and the plan. Its embedded plan was checked against the immutable commit linked above and matches after trimming surrounding whitespace.
- [ChatGPT Round 2 response](Anthony_ChatGPT_Round2_Response.txt) is preserved from the file delivered to Anthony.
- Obtain Claude's actual cross-review of ChatGPT's initial critique and record its model/version and chat link. The supplied initial critique does not substitute for that step.
- Add course-accessible links for both model conversations. The local Codex link above does not meet that requirement by itself.
- Have the team record its final decision, including whether to add a real-request study. Do not close #15 until the missing evidence is recorded.
