# Team roles and handoffs (proposal, for discussion)

*Proposed by Spencer on 2026-09-23, updated 2026-09-29. Anthony: comment on anything in the pull request. Nothing here is final until we both approve and merge it.*

## The idea: one person per half of the project

CacheShift has two halves that meet at a clear boundary: the **gateway** (the product that answers questions) and the **measurement** (the test set and the analysis that says what the gateway did). Each of us owns one half end to end, reviews the other's pull requests, and shares the course deliverables.

| | Anthony: the gateway | Spencer: the measurement |
|---|---|---|
| **Owns** | The server app, cache, router and model connections | The test set, the experiments, the statistics |
| **Builds** | OpenAI-style endpoint; semantic cache (embeddings + similarity threshold); RouteLLM router integration; replay backend (recorded answers) and live backend (real APIs); request logging | RouterBench download and question selection; rewordings and the human check; question streams; tuning and test splits; experiment runner; drift, false-hit and inherited-error metrics; confidence intervals; re-tune calculation |
| **Early risk tests** | Gateway runs end to end in replay mode (Sprint 1) | Drift test A2 and rewording check A3 (Sprint 1) |
| **Stretch goals** | Load and failure testing; production-style proxy | Measured energy on the BU GPU (RQ4) |

**Shared:** user conversations (each of us runs at least one), sprint reports, demos, the poster, and reviewing every pull request the other person opens. We rotate the sprint lead each sprint.

**Why this split:** the halves can be built in parallel from day one, each of us has a clear thing to demo, and the review step means each of us understands the other's half.

## The two handoffs (agree on these first)

Everything else can change, but these two formats let us work in parallel without waiting on each other. Draft versions:

**1. Test-set file (Spencer → Anthony).** One row per question:

| Field | Meaning |
|---|---|
| `question_id` | Unique ID |
| `group_id` | Same for an original question and all its rewordings |
| `text` | The question as asked |
| `is_original` | True for the benchmark's own wording |
| `gold_answer` | The benchmark's human-written correct answer |
| `source` | Benchmark name (MMLU, GSM8K, …) |
| `split` | `tuning` or `test` |
| `answers` | For each model: recorded answer, whether it was correct, and its cost |

The replay backend looks up `answers` instead of calling a model.

**2. Gateway log (Anthony → Spencer).** One row per request the gateway handles:

| Field | Meaning |
|---|---|
| `request_id`, `timestamp` | Which request, and when |
| `question_id` | Links back to the test set |
| `config_id` | Which experiment settings were used (budget, threshold, repetition rate, seed) |
| `cache_hit` | True or false |
| `similarity` | Best similarity score found in the cache |
| `matched_question_id` | Which stored question the cache matched (on a hit) |
| `router_score` | The router's score for this question (on a miss) |
| `route` | `cache`, `strong` or `weak` |
| `model` | Which model answered (or which model's stored answer was reused) |
| `answer` | The answer returned |
| `cost_usd`, `latency_ms` | What it cost and how long it took |

Correctness is added afterwards by comparing `answer` with `gold_answer`, never by an AI.

## Proposed Sprint 1 assignments

| Who | Task | Done when |
|---|---|---|
| Spencer | Agree the two handoff formats with Anthony | Both formats merged in this file |
| Spencer | Small sample test-set file (~100 questions with rewordings) | Anthony can build against real data |
| Spencer | Drift test (A2) | Short write-up: do cache misses score differently from all questions? |
| Spencer | Rewording check (A3) plan, run if the API budget allows | Agreement rate between originals and rewordings |
| Anthony | Bare-bones gateway in replay mode | One cache setting, one router, one budget, end to end, writing the log format above |
| Both | Outreach and one conversation each (A1) | Notes from each conversation in `docs/sprints/Sprint_1/` |
| Both | AI review of the Sprint 1 plan: two different models critique it, then each other's critique (course requirement) | `docs/sprints/Sprint_1/AI_Review_Log.md` filled in, with chat links and the one change we made |
| Both | Sprint 1 report and demo | `docs/sprints/Sprint_1/README.md` filled in |

## Open questions for Anthony
1. Does this split match what you want to work on? Happy to swap pieces, e.g., if you'd rather own the re-tune command or the energy stretch.
2. Any changes to the two handoff formats?
3. Who leads Sprint 1?
