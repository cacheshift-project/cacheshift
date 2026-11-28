# Uneven repeats: protocol (fixed before any run)

**Written 27 Nov 2026, committed before the runs below.** It follows the Sprint 3 next step "check whether easy questions repeating more change how often the expensive model is used".

## Question
Real users ask easy questions more often than hard ones. Suppose the router's cutoff was set on the app's traffic **before** the cache was added, so on traffic that includes those repeats. Does turning the cache on then move the expensive-model share away from the plan, and by how much?

**Why the comparison has to be set up this way.** With the cache on, the router sees roughly each question once, however uneven the repeats are. So uneven repeats can only shift the share relative to a router tuned on traffic without a cache. That is the original A2 worry ("caching breaks routing budgets"). Sprint 2 tested it on real LMSYS traffic (+2.2 points [+0.3, +4.1]) and with engineered router-score skews (#37). This test uses a skew a builder would recognise and that does not come from the router: **topic level**.

## Data and setup
- **Questions:** the full MMLU set from the re-tuning-at-scale protocol (`data/mmlu_all_20261127/`, SHA-256 `95c9030845ca1a9f64656c0fa41840420d516740c2f6be4e3992f626c9d84cca`).
- **Topic level comes from the subject name only:**
  - **Easy:** `elementary_*` and `high_school_*`, 15 subjects (1,842 test / 1,835 tuning questions).
  - **Hard:** `college_*` and `professional_*`, 10 subjects (1,645 / 1,642).
  - **Other:** everything else (3,388 / 3,372).
- **Streams,** built for each split the same way: every question once, plus the same number of repeats (repeat fraction 0.5), drawn with weights and shuffled (seed 601). Three policies:
  - **uniform:** every question weight 1.
  - **easy-repeat:** easy questions weight 3, others 1. This is the primary policy.
  - **hard-repeat:** hard questions weight 3, others 1, as the mirror check.
- **Cutoff, per policy:** set so 50% of the **tuning stream's** requests, repeats included, go to the expensive model with no cache (`calibrate_scores` on every request's router score). That is "tuned on the traffic before the cache".
- **Runs, per policy, on the test stream:** no cache, and semantic cache at 0.90, both with that policy's cutoff. Everything else (router, single-question scoring, MiniLM, `ReplayGateway`, recorded answers) is as in the Sprint 3 demo.

## Outcomes and decision rule
Ranges are 95% bootstrap intervals over question groups (2,000 resamples, seed 601), via `report.build` with the no-cache run as the fresh log.

- **Primary:** for **easy-repeat**, the cache's own effect on the expensive-model share (cache minus no cache, same stream, same cutoff, paired by group). The verdict is `report.band_verdict` against ±3 points:
  - **outside** (estimate and whole range beyond ±3): with easy questions repeating more, the cache does push the router off its budget.
  - **within:** it doesn't, at this skew.
  - **unsure** versions: too few questions to tell.
  - **Expected direction** (stated before running): positive. The cache removes the extra easy repeats, so the router sees relatively more hard questions.
- **Secondary:**
  - The same effect for hard-repeat (expected negative) and uniform (expected about 0).
  - Each run's drift from the 50% plan.
  - The cache's accuracy change vs fresh answers.
  - Cost per 1,000 with and without the cache.
  - Whether topic level relates to router score at all: the mean router score of easy vs hard test questions.

All results are reported whatever they show.

## Limits (state on the poster)
- Topic level is a stand-in for "easy". A 3× weight is one chosen skew, not measured user behaviour.
- MMLU multiple choice only, exact repeats, recorded answers, one seed.
