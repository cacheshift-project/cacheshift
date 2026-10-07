# Story 3 — subject-balanced calibration

## Protocol fixed before MMLU router scoring

The ARC development evaluation missed the 50% target by 3.33 points. A subsequent
fresh-relative-to-fixture ARC test missed by 5.05 points. Keep both failures; do
not tune a cutoff using those test scores or reinterpret their accuracy intervals
as proof of equivalence. The next design improves calibration coverage and sample
size, not the router's model weights or the quantile objective.

Use the untouched local MMLU subset of the verified RouterBench zero-shot file.
Join the official `cais/mmlu` test answer keys by subject, normalized stem and
unordered choice texts, remapping the correct answer to RouterBench's order.
Reject ambiguous/conflicting keys. Families are normalized stems across subjects;
retain one canonical subject/record for duplicate families. Select 64 families
per subject by SHA256(`601:` + stem), put the first 32 in tuning and the remaining
32 in test. All subjects must have sufficient aligned families; do not silently
reduce a subject sample or substitute subjects based on outcomes.

Use the existing miss-only quantile fit, fixed CPU checkpoint, target 50%, cold
unbounded exact cache, uniform 50% repeats, seeds 601–605 and 2,000 paired
question-family bootstrap samples. Fit baseline and retuned cutoffs on tuning
only. Test evaluation starts after fitting. Do not change sample, target, seed,
cutoff or acceptance rule after observing test results. Report every seed and
every failed check; a failure remains a failure.

Success means 47–53% of cache misses routed to the strong model and retuned
accuracy inside the paired no-cache run's marginal 95% accuracy interval for all
five seeds. This is the issue's descriptive quality criterion, not a statistical
non-inferiority/equivalence claim. Seeds repeat the same question pool.

This balanced mixture is a controlled replay experiment. Passing it does not
erase ARC failures, prove drift on real requests or guarantee production shares.
Released-router training may overlap MMLU. No live APIs, semantic cache or energy
measurement are involved.

## Reproduce

Install `.[dev,data]` and the CPU router dependencies in `RouteLLM_Feasibility.md`.
From the repository, with new output directories:

```powershell
.venv/Scripts/python.exe tools/build_mmlu_retune.py --routerbench ../data/routerbench/routerbench_0shot.pkl --download-keys --output data/my-mmlu-retune
.venv/Scripts/python.exe -m cacheshift.retune --dataset data/my-mmlu-retune/questions.jsonl --run-dir experiments/results/my-mmlu-retune
```

The official Parquet key file is pinned to repository revision
`c30699e8356da336a370243923dbaf21066bb9fe` and SHA-256
`74a41822ce7d3def56e1682f958469c04642a5336a5ce912fa375fdb90fb25d7`.
The RouterBench pickle is digest-checked before loading. Dataset output uses
canonical LF bytes so calibration hashes survive Windows/Unix checkouts.

The builder aligned 13,896 records. It excluded 142 with unavailable/invalid
recorded responses or costs and four with ambiguous correct choice text. These
filters enforce the declared replay/key contract, not answer correctness or router
scores; missing response coverage may still bias the eligible population. The
selected pool contains 3,648 distinct families, equally divided between tuning
and test. Its SHA-256 is
`3821ecbbb123d496f59efc601dec2686427f3e7e6506e3ea6275097c82c8f241`.

CPU inference now supports small batches, preserving the pinned checkpoint,
token limit and probability definition. Prefetch happens separately for tuning
and test; test scoring begins only after cutoffs are written. Six existing ARC
development prompts differed from individual inference by at most
`7.57e-8` in strong-model score. Batching changes computation efficiency, not the
calibration objective. Both single/batch equivalence and stage isolation have tests.

Validation before evaluation results: 55 tests passed. A key-alignment audit found
no differences from RouterBench's recorded strong-model correctness and five
weak-model differences out of 3,648 selected rows. Those five responses have an
unclosed bracket such as `[B`; our pre-existing strict answer parser marks them
incorrect. Keep that rule and those rows unchanged rather than relaxing grading
after inspection. This audit checks source alignment, not a routed-accuracy result.
