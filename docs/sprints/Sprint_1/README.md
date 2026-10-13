# Sprint 1

**Dates:** 28 Sep to 12 Oct 2026  ·  **Demo:** 13 or 14 Oct (2-minute presentation)

## Goal
Retire the feasibility risk (data, router and a replay gateway running on both laptops) and run the cheapest test of A2: does a cache shift the router's strong-model share?

## Committed stories
Sprint 1 committed the feasibility tasks and touched four of the five user stories. ☑ done · ◐ partly · ☐ not done.

| Issue | Owner | Acceptance criteria | Done? |
|---|---|---|---|
| #8 RouterBench loader | Spencer | Script downloads and summarizes RouterBench; sample committed; runs on Anthony's laptop | ☑ PR #20 (36,497 questions, 11 models; pinned digest after review) |
| #10 RouteLLM on 10 questions | Anthony | Scores 10 questions locally; router choice recorded | ☑ PR #21 (BERT router, laptop CPU) |
| #11 Bare-bones replay gateway | Anthony | One cache, router and budget end to end; agreed request log | ☑ PR #22 |
| #15 AI review of the plan | Both | Two models, cross-reviews, chat links, one change | ☑ PRs #20, #24 |
| #16 Faculty list | Both | 2–3 BU professors, a paper and a question each | ☑ PR #19 (Coskun, Crovella) |
| #17 Finalize SPRINT1.md and TEAM.md | Both | No TODOs; board link; Osama and TA added | ◐ Docs done; collaborators not added yet (usernames requested) |
| #12 Drift test (A2) | Spencer | Write-up with the key number and a margin of error; reproduced | ◐ Controlled results: no drift with random repeats (PR #23); clear drift when repeats are deliberately skewed (PR #28). Real-traffic part moved to Sprint 2 |
| #9 API key check | Anthony | One real call from `.env`; Spencer repeats it | ☐ Script and mocked tests only; no real call |
| #13 Rewording check plan (A3) | Spencer | Sample size, models, cost estimate | ☐ Not started |
| #14 Name the target user (A1) | Both | Three candidates contacted; one named | ☐ No one contacted yet; first three messages planned for 16 Oct |
| #5 Story 3: re-tune command | Anthony | Re-tuned share within ±3 points of plan; accuracy within no-cache margin | ◐ Missed the ±3-point target on ARC (53.3%, 55.1%; PRs #23, #27). On a pre-declared balanced MMLU set it lands at 50.99% (PR #28), but that set showed no cache drift. A controlled test with deliberately skewed repeats does show drift (41–44% or 57–58% instead of ~51%); re-tuning returns to 50.99%, but with an exact cache that is guaranteed by design (#29), so drift correction is not yet proven |
| #6 Story 4: app switches by URL | Anthony | Example app switches by changing one web address; valid request log | ☑ PR #27: the unchanged SDK app switches by base URL; the repeat is a cache hit; all 13 log fields present (replay mode only) |

## Demo
- **What we show:** the replay gateway end to end (`python -m cacheshift.demo`): 15 questions run through cache → router → recorded answer, once without the cache and once with it, and each request is logged. With the cache, 5 of 15 are cache hits and the strong model's share of routed requests goes from 66.7% to 80.0%. Fifteen requests is far too few to mean anything; the demo shows the pipeline works.
- **What worked live:** [fill in after presenting]
- **What is not real yet:** answers are recorded RouterBench answers (replay mode), not live model calls, and the cache matches exact repeats only, not similar questions.
- **Slides:** [Sprint1_Presentation.pdf](Sprint1_Presentation.pdf)

## Retro
- **What worked:**
  - Feasibility was proven early: data, router and gateway run on both laptops with no GPU and no API bill.
  - Code review caught real problems: Anthony found a security hole in the RouterBench loader (a pickle could write files), and a merge that would have reverted the review log was caught before it landed.
  - The two-model AI review changed the plan (A2 in two parts, explicit share denominators, extra baselines), and our own data confirmed its main prediction.
- **What broke:**
  - The plan was due 5 Oct and fully merged on 7 Oct: a GitHub Actions outage blocked merges, and stacked pull requests caused conflicts.
  - Resolving those conflicts twice reverted already-finished files; we also kept status in three places (the board, `Remaining_Issues.md`, PR descriptions) that drifted apart.
  - The riskiest assumption (A1, a real user) got no test: nobody was contacted.
  - Work was uneven: most Sprint 1 code came from the gateway side, and the measurement tasks (#12, #13) slipped.
- **What we're changing next sprint:**
  - User outreach first, tracked on the board, before any new experiment.
  - Smaller pull requests, one topic each, updated from `main` before review; no stacked PRs unless we agree.
  - The board is the single status record; sprint docs link to it instead of repeating it.
  - Each of us ships work on our own half every week; review within 24 hours (TEAM.md).

## Assumptions tested this sprint
| Assumption | Test | Result | Pivot? |
|---|---|---|---|
| A1: engineers would use a drift report | Three 15-minute conversations | **Not tested.** No one contacted yet | Not yet; pivot line stands (end of Sprint 2) |
| A2: a cache shifts the router's strong-model share | Exact cache, random repeats, 300 ARC questions, 5 seeds, paired bootstrap | Cache effect −1.7 to +2.2 points; every 95% CI includes 0. Random repeats give no drift | Changed the test: A2 now also checks real chat logs (do repeated prompts score differently?) |
| A3: rewordings keep replay valid | Not run | Not tested | No |
| A4: routers are tuned to a budget percentile | Read RouteLLM's calibration code | Verified | No |
| Feasibility: data, router, gateway, API | Run on both laptops | Data, router and gateway work; real API call not made yet | No |

## LLM chat links used this sprint
<!-- Required in every report. -->

- AI review of the plan (#15): [Claude, rounds 1 and 2](https://claude.ai/share/1a046ff9-6cb9-41ad-8612-4ea083ce692d) · [ChatGPT/Codex, rounds 1 and 2](https://chatgpt.com/s/cx_6ac6b43910a08191ad25a9785a6d87cf). Full log: [AI_Review_Log.md](AI_Review_Log.md).

- RouterBench loader (#8), plan drafting, this README and the Sprint 1 slides: Claude Code assisted with the loader, its safety tests, SPRINT1.md, TEAM.md, the review log, this report and the presentation draft. Local session (Claude Code has no public share link).

- Issues #5, #6, #9 and #15: Codex assisted with the endpoint, SDK example, tuning-only re-calibration, evaluation, API helper and ChatGPT review. [Implementation and remaining acceptance checks](Remaining_Issues.md). [Codex session (public share)](https://chatgpt.com/s/cx_6ac6b43910a08191ad25a9785a6d87cf). No paid API success or completed #5 acceptance is claimed.

- Replay gateway and demo (#11): Codex assisted with the implementation, tests, and documentation. [Codex session (public share)](https://chatgpt.com/s/cx_6ac6b43910a08191ad25a9785a6d87cf). See [the run instructions and evidence](Replay_Gateway_Demo.md).

- RouteLLM feasibility implementation and tests: Codex assisted with inspecting the official router, implementing the CPU adapter, and documenting validation. [Codex session (public share)](https://chatgpt.com/s/cx_6ac6b43910a08191ad25a9785a6d87cf).

- Faculty research and document drafting: Codex assisted with source research and drafting. [Codex session (public share)](https://chatgpt.com/s/cx_6ac6b43910a08191ad25a9785a6d87cf).

## Faculty connections

[CacheShift faculty document](CacheShift_Sprint1_Faculty.docx) covers Ayşe Coskun and Mark Crovella, with a relevant paper, project connection, and a specific question for each. These are proposed questions, not completed faculty conversations.
