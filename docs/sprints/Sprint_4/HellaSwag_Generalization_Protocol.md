# Does the difference check generalize? HellaSwag protocol (fixed before any run)

**Written 27 Nov 2026, committed before the runs below.** The difference check ([Difference_Check_Protocol.md](Difference_Check_Protocol.md)) was designed after the MMLU template finding. A fair question is whether it only works on MMLU. Here it runs **unchanged** on a dataset it has never seen.

## Data
- **Questions:** every RouterBench HellaSwag question, 10,042 rows: `hellaswag.val.N` is HellaSwag validation item N.
- **Answer keys:** the official HellaSwag validation set, `Rowan/hellaswag` at revision `218ec52e09a7e7462a5400043bb9a69a41d06b76`, file SHA-256 `899813071e1e95efafec90f856e1987d2150fa4d020fc005df6962c259f660cd`.
- **Alignment check:** each RouterBench prompt matches its item's context and all four endings, after normalizing whitespace (10,042 of 10,042 checked). RouterBench shows the endings in a different order, so the key is remapped to the letter of the official correct ending as shown. A row is skipped if its recorded response or cost is unusable, or the remap is ambiguous; skipped rows are listed in the manifest.
- **Groups and split:** a question group is HellaSwag's `source_id` (one video or WikiHow article), so related questions stay together. Groups are ordered by SHA-256("601:" + source_id): the first half (rounded down) is tuning, the rest test. No model outcome or score is used.
- **Models:** GPT-4 is the expensive model and Mixtral the cheap one, as before.

## Runs (the same pipeline as the MMLU difference check)
- The router's cutoff is set on the tuning questions to a 50% plan.
- The stream is every test question plus uniform repeats (seed 601).
- Runs: no cache; cache 0.90; cache 0.90 + difference check 0.80. **The check's code and setting are unchanged.**
- Then the safe setting finder on the same traffic (limit 0.5%).

## Outcomes
Ranges are 95% bootstrap intervals over question groups.

- **Primary:** wrong answers caused by the cache at 0.90 + check, against 0.90 without it. The verdict:
  - **Generalizes:** with the check, the top of the range is below 1% of requests, and the estimate is lower than without it.
  - **No problem to fix:** without the check, the top of the range is already below 1%. Then only the check's cost (fewer answers from the cache) is informative.
  - **Does not generalize:** with the check, the top of the range is at or above 1%.
- **Secondary:** answered from the cache, accuracy against fresh answers, cost per 1,000, expensive-model share, the setting finder's recommendation, and the main kinds of question behind any wrong answers that remain.

Every outcome is reported, whatever it shows. Nothing here changes the MMLU or ARC results.

## Limits
- One stream seed.
- HellaSwag is sentence completion with four endings: closer to a chat question than MMLU, but still a benchmark.
