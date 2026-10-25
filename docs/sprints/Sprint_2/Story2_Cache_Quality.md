# Story 2 (#4): what does a cached answer cost in quality?

*Spencer · 2026-10-12 · results: [`experiments/results/cache-quality-20261012`](../../../experiments/results/cache-quality-20261012/report.md)*

**Acceptance criteria (#4)**
- [x] False hits and inherited errors reported separately per cache setting, with 95% confidence intervals
- [x] A hand check of 50 cached answers agrees with the automatic labels at least 90% of the time: **96% (48/50), passed** (below)

## What we built

- `src/cacheshift/semantic_cache.py`: a semantic cache. Prompts are embedded with `all-MiniLM-L6-v2` on a laptop CPU; a hit is the most similar stored prompt at or above a cosine threshold. `threshold=None` is an exact-text cache.
- `src/cacheshift/cache_quality.py`: replays a question stream through the cache at six settings (exact, and cosine ≥ 0.98, 0.95, 0.90, 0.85, 0.80), for GPT-4 and Mixtral recorded answers, over five seeds. Every served answer is graded against the **official ARC answer key** (never an AI). Each hit gets one automatic label:

| Label | Meaning |
|---|---|
| hit_ok | matched the same question; stored answer right |
| inherited_error | matched the same question; stored answer was already wrong |
| false_hit_error | matched a **different** question; served answer wrong for this one |
| false_hit_lucky | matched a different question; served answer happens to be right (multiple choice) |

- `tools/hand_check.py`: draws 50 hits into a blind sheet (no automatic labels shown) and scores a person's answers against the hidden labels.

**Data:** the 970-question ARC holdout from PR #27 (official keys; not used for any tuning here). Stream: every question once plus the same number of uniform repeats (repeat fraction 0.5), seeds 601–605. Intervals: percentile bootstrap over question groups, 2,000 resamples.

## Results (seed 601; the other seeds agree, ranges below)

| Cache setting | Hit rate | False hits (per request) | Inherited errors (GPT-4 / Mixtral) | Accuracy change vs. fresh (GPT-4) |
|---|---:|---:|---:|---:|
| exact | 50.0% | 0.0% | 2.2% / 8.5% | 0.0 |
| cos ≥ 0.98 | 50.2% | 0.2% [0.0, 0.4] | 2.2% / 8.5% | −0.1 pt [−0.3, 0.0] |
| cos ≥ 0.95 | 50.3% | 0.3% [0.1, 0.5] | 2.2% / 8.5% | −0.2 pt [−0.4, −0.1] |
| cos ≥ 0.90 | 50.4% | 0.4% [0.1, 0.7] | 2.2% / 8.5% | −0.3 pt [−0.5, −0.1] |
| cos ≥ 0.85 | 50.7% | 1.2% [0.5, 2.2] | 2.2% / 8.3% | −1.0 pt [−2.0, −0.3] |
| cos ≥ 0.80 | 51.6% | 3.2% [2.0, 4.6] | 2.2% / 8.2% | −2.5 pt [−3.9, −1.4] |

Across all five seeds (GPT-4): accuracy change at cos ≥ 0.90 ranges −0.26 to −0.57 points; at cos ≥ 0.80, −2.01 to −2.53. Mixtral is similar (full table in `report.md`, every run in `report.json`).

## What it means

1. **Loosening the threshold buys almost no hits here and costs accuracy.** Going from exact to cos ≥ 0.80 adds 1.6 points of hit rate but serves a wrong question's answer to about 3% of requests and loses about 2.5 points of accuracy. Nearly every hit in this workload is an exact repeat, because we have no rewordings yet.
2. **Benchmark near-twins are close.** The most similar *different* question has median cosine 0.65, 99th percentile 0.94, maximum 0.995, so even cos ≥ 0.98 produces a few false hits.
3. **A false hit sticks.** A question served from another question's entry is never stored itself, so every later repeat of it gets the same wrong answer.
4. **Inherited errors are frequent but free in replay.** They are 2.2% (GPT-4) and 8.5% (Mixtral) of requests: the model's own wrong answers, repeated. Re-asking a question in replay mode returns the identical recorded answer, so they cost nothing versus a fresh call here; with live models (which vary) they could.

**Limits:** uniform repeats; no rewordings (Story 5), so true semantic hits are not yet tested and the benefit side of a semantic cache is understated; full prompts are embedded, including the shared answer-format instruction, which raises every pair's similarity; ARC multiple choice only; labels are automatic until the hand check passes. Many of the highest-similarity false hits (cosine 0.96–0.995) are the same question with its answer choices shuffled: the cache reuses a letter that now points to a different choice. That is partly a multiple-choice artifact (a free-text answer would often still be right), so the false-hit cost here may overstate what a chat app would see at the strictest settings. A clearer example at cos ≥ 0.90 is a genuinely different question: "A definite shape and a definite volume are properties of which state of matter?" matched to "A substance in the solid phase of matter has…", which served answer A ("liquid and gas" in the new question).

## Hand check (the remaining acceptance step)

The sheet has 50 rows: 25 false hits (19 wrong, 6 lucky), 12 inherited errors and 13 correct same-question hits, across all six settings and both models. **Do not open `hand_check_key.json` until the sheet is filled in.**

1. Open `experiments/results/cache-quality-20261012/hand_check_sheet.csv` (Numbers, Excel or Google Sheets).
2. For each row, fill two columns with `Y` or `N`:
   - **same_question**: is `matched_question` the same question as `query_question`? (Same wording and the same answer choices; a different item with a similar stem is `N`.)
   - **served_correct**: is `served_answer` the right answer to `query_question`, according to `answer_key`? (A letter with or without a bracket counts; a different letter, or an answer that isn't a single choice, is `N`.)
3. Use `notes` for anything odd. Save as CSV with the same name.
4. Score it:

```bash
python tools/hand_check.py score --sheet experiments/results/cache-quality-20261012/hand_check_sheet.csv --key experiments/results/cache-quality-20261012/hand_check_key.json
```

The story passes if both labels agree on at least 90% of rows (`passes_90_percent: true`). Record the result and any disagreements here.

**Hand-check result (Spencer, 2026-10-25, blind):** agreement **48/50 = 96%** on both labels together (95% Wilson interval 86.5–98.9%), so the story passes. `served_correct`: 50/50. `same_question`: 48/50. Both disagreements (items 32 and 45) are exact repeats with word-for-word identical question text, so the automatic label ("same question") was right and the two "N" answers were reviewer slips; item 32 is an inherited error, where the wrong stored answer made the repeat look like a different question. The blind answers are kept as entered. Re-score with the command above.

## Reproduce (macOS)

```bash
pip install -e ".[dev,cache]"
python -m cacheshift.cache_quality --run-dir experiments/results/my-cache-quality
```

The first run downloads `all-MiniLM-L6-v2` (about 90 MB) to `data/cache/embeddings/` (gitignored). The full run takes under a minute on a laptop CPU; no GPU or API key. Every hit for the first seed is written to `raw/` (gitignored; its SHA-256 is in `report.json`).
