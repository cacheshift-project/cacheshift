# Sprint 1 — AI review of the plan

The course asks two *different* AI models (not two chats with the same one) to review the Sprint 1 plan and argue about it. The AIs advise; the team decides.

**Review status:** ChatGPT/Codex review recorded below on 2026-10-04. Claude's review and both cross-reviews are pending; issue #15 is not complete.

**Models used:** ChatGPT/Codex in Anthony's current chat. Claude has not been run for this record. The accessible Claude browser session requires login.
**Plan reviewed:** [`SPRINT1.md` at 4835a60c258543cb6a132bc59b55ab4cfa459ca8](https://github.com/cacheshift-project/cacheshift/blob/4835a60c258543cb6a132bc59b55ab4cfa459ca8/SPRINT1.md), before the evaluation correction in this PR.

## Step 1 — same plan, same three questions, to both models

1. What is our riskiest unstated assumption?
2. Why might this fail by week 6?
3. What is missing from our evaluation?

| Question | Claude's answer (summary) | ChatGPT's answer (summary) |
|---|---|---|
| Riskiest unstated assumption | Pending actual Claude review | That planned strong-model share is both a stable no-cache test baseline and an adequate proxy for a monetary budget. A tuning percentile does not guarantee the same share on test data, and token lengths can change cost even at a fixed share. Section 8 currently assumes the no-cache share equals the plan. |
| Why it might fail by week 6 | Pending actual Claude review | The team could spend its time integrating semantic caching, rewordings, APIs and energy measurement before defining a valid paired experiment. Recorded answers do not establish fresh-model behavior on paraphrases; if A3 fails, the paid-call budget and timeline may not support the proposed sweep. Keep an originals-plus-exact-repeats baseline and treat semantic and live results as separate stages. |
| Missing from our evaluation | Pending actual Claude review | Explicit share denominators; measured no-cache test calibration error; paired cache-on/off and retuned/untuned comparisons; question-group bootstrap for dependent repeats; achievable targets under tied scores; a frozen tuning protocol; and a quality non-inferiority margin. Being inside the baseline accuracy CI does not prove equivalent quality. |

Chat links: Claude pending · [ChatGPT/Codex local conversation](codex://threads/01a0cffd-318f-7100-846f-41901b98be6d). This is a local application link, not a public share link; a course-accessible link still needs to be supplied before submission.

## Step 2 — cross the reviews

Give each model the other's critique and ask it to attack or defend it.

- Claude on ChatGPT's critique: pending actual response.
- ChatGPT on Claude's critique: pending Claude's initial review. No second-model response has been invented.

Chat links: both cross-review links pending.

## Step 3 — what we take from it

**Where they agreed** (probably a real problem):
- Pending both reviews; no agreement is claimed.

**Where they disagreed** (what we decided, and why):
- Pending both reviews and the team's decision.

**The one change we made to the plan because of this review:**
- Proposed in this PR from the ChatGPT review: correct Section 8's baseline assumption and specify the denominator, paired comparisons and tuning/test separation. Teammate review is still required before merge; this is not represented as a completed two-model consensus.

## Completing the Claude review

Give Claude the immutable plan linked above and the three Step 1 questions, without this review initially. Save its model name, date, full response and share link. Then give Claude the ChatGPT column above and ask which points it supports or rejects, with reasons. Bring Claude's original critique back to this conversation so ChatGPT can cross-review it. Add both real cross-review links and the team's decision here. Do not close #15 until these steps and usable chat links are complete.
