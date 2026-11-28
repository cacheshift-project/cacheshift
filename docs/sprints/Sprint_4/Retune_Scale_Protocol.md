# Re-tuning at scale: protocol (fixed before any run)

**Written 27 Nov 2026, committed before the runs below.** It follows the Sprint 3 next step "Use more questions". The Sprint 3 demo (970 ARC requests) could not tell whether re-tuning brings the expensive-model share back within ±3 points on new questions, because the held-out range was 48.8% to 61.9%.

## Question
With about 14 times as many questions, does re-tuning the router's cutoff on the traffic it has seen bring the expensive-model share within ±3 points of the 50% plan **on questions it was not fitted to**? What does that cost in accuracy?

## Data
- `data/mmlu_all_20261127/`: every RouterBench MMLU question with an official answer key. It is built with `python tools/build_mmlu_retune.py --routerbench data/raw/routerbench_0shot.pkl --download-keys --all-families --output data/mmlu_all_20261127`.
  - Dataset SHA-256 `95c9030845ca1a9f64656c0fa41840420d516740c2f6be4e3992f626c9d84cca`.
  - 13,724 questions in 57 subjects: 6,849 tuning and 6,875 test. 146 RouterBench rows were skipped (142 invalid recorded responses, 4 ambiguous keys).
  - The split uses the existing rule: per subject, stem families ordered by SHA-256("601:" + stem), the first half tuning and the rest test. No model outcome or score is used.
- The questions file is 17 MB, so it is not committed. The manifest is, and the build is deterministic.

## Setup (same pipeline as the Sprint 3 demo)
- **Router:** RouteLLM BERT router, pinned revision, single-question scoring. Its cutoff is set on the **tuning** questions to a 50% expensive-model share (`replay_gateway.calibrate`).
- **Cache:** semantic cache at 0.90 (MiniLM, `semantic_cache`).
- **Stream:** each test question once plus uniform repeats (`cache_quality.request_stream`, repeat fraction 0.5, seed 601), so about 13,750 requests.
- **Gateway:** each request goes through `ReplayGateway.answer` in-process. That is the same object the HTTP gateway serves; the HTTP hop is skipped for time.
- **Answers:** recorded answers and costs from RouterBench (GPT-4 expensive, Mixtral cheap). No live calls.

## Runs
1. No cache.
2. Cache at 0.90, original cutoff.
3. Cache at 0.90, cutoff re-tuned on half A: `retune_log.fit` on run 2, where half A is the question groups with an even SHA-256(group).
4. Cache at 0.90, cutoff re-tuned on half B (the odd groups), for the cross-fit check.

## Outcomes and decision rule
Ranges are 95% bootstrap intervals over question groups (2,000 resamples, seed 601), as in the report.

- **Primary.** Run 3 vs run 2 on held-out half B, which is exactly the report's "Re-tune the router?" card (`report.retune_comparison`). The verdict is the report's `band_verdict` on the re-tuned share's drift from 50%:
  - **within** (estimate and whole range inside ±3): re-tuning works at this scale.
  - **within-unsure:** probably works, but still too few questions to be sure.
  - **outside-unsure / outside:** re-tuning on seen traffic does not carry over to new questions here.
- **Secondary.**
  - The accuracy change from re-tuning (paired, held-out half) against the −1.0-point margin from #37, and the cost change.
  - Cross-fit: each half judged with the cutoff fitted on the *other* half (run 4 on half A, run 3 on half B), pooled over all groups. Every question is checked with a cutoff not fitted to it, so the range is narrower. The verdict uses the same rule.
  - The original cutoff's drift on the full test stream, and the cache's own effect on the share (run 2 vs run 1, paired), as in the Sprint 3 report.

All of these are reported whatever they show. If the primary result is "within-unsure", we say that, and don't pick whichever secondary looks best.

## Limits (state on the poster)
- MMLU multiple choice only, with exact repeats drawn uniformly. Reworded questions and uneven repeats are tested separately.
- These are recorded historical answers and costs, not live calls.
- The RouteLLM router may have seen MMLU-like data in training (see the manifest's limitation note).
- One seed.
