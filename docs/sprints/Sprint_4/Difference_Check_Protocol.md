# Difference check: protocol (fixed before any run)

**Written 27 Nov 2026, committed before the runs below.** It follows the unplanned finding in [Sprint4_Experiment_Results.md](Sprint4_Experiment_Results.md). At 0.90 the semantic cache caused 567 wrong answers on MMLU (4.1%), mostly in questions that share a long identical lead-in ("moral scenarios") or passage (history). The similarity was dominated by the shared text, so the cache matched the template rather than the question.

## The fix
- **The check.** When the cache finds a saved question at or above its match setting, it checks the match before reusing the answer:
  1. Remove the words the two prompts share at the start and at the end (the longest common leading and trailing run of whitespace-separated words).
  2. What is left in each prompt is the part that differs. Embed both with the same MiniLM model.
  3. Reuse the answer only if those two parts are at least the **check setting** alike.
- **Edge cases.** If nothing is left in either prompt, the prompts are the same text and the match passes. If only one has text left, it fails.
- **Up to 5 candidates.** The cache tries the saved questions at or above the match setting, best first, and reuses the first that passes. If none passes, it's a miss.
- **What it sees.** It uses only the two prompts' text: no labels, answers or router scores. It's built from what was seen on ARC and in the examples quoted in the Sprint 4 write-up. Its settings are fixed here, before it is run on MMLU.

## Runs
- **Same pipeline as Re-tuning at scale.**
  - The full MMLU set (SHA-256 `95c903…f8c241`), and the same stream: test questions plus uniform repeats, seed 601, 13,750 requests.
  - The same cutoff (0.4548) and router scores.
  - Paired against that run's no-cache log.
- **MMLU.**
  1. Cache 0.90 with the check at **0.80** (primary).
  2. Cache 0.90 with the check at 0.70 and at 0.90 (sensitivity).
  3. Cache 0.80 with the check at 0.80 (can the match setting be loosened safely?).
- **ARC, the Sprint 3 demo stream** (970 requests, seed 601). Cache 0.90 and 0.80, each with the check at 0.80, as a no-regression check against the Sprint 3 runs.
- **The 120 rewordings.** The full-prompt lookup from the reworded check at 0.90 and 0.80, with the check at 0.80, to show what the check costs on true rewordings. These count only after the #7 hand check.

## Outcomes
Ranges are 95% bootstrap intervals over question groups, as in the report.

- **Primary:** wrong answers caused by the cache (another question's saved answer, wrong for this question) at cache 0.90 + check 0.80, against 567 (4.12% [3.64, 4.66]) without the check. Success is that the range's upper end is below 1% of requests.
- **Secondary:**
  - Accuracy against fresh answers (was −1.7 [−2.2, −1.3]).
  - Answered from the cache (was 52.8%) and cost per 1,000 (was $0.33).
  - The expensive-model share.
  - The sensitivity runs.
  - On ARC: wrong answers caused (0 at 0.90 in Sprint 3; 20 at 0.80) and hit rate.
  - On the rewordings: caught out of 120.

All of these are reported whatever they show.

## Limits
- One stream seed.
- The 5-candidate limit and the word-level trimming are design choices that were not tuned.
- A real template can vary its wording (dates, names), and then nothing is shared to trim.
