# Re-tuning follow-up: diagnose before changing the method

2026-10-05. This is follow-up work for #5, not an acceptance pass.

The current cutoff fits 100 of 200 tuning questions to the strong model, exactly
the declared 50% target. The previously evaluated test split routes 160 of 300
questions to the strong model (53.33%; seed 601 group-bootstrap 95% interval
47.33–59.33%). This fails the issue's point-estimate requirement of 47–53%, even
though the target lies inside the interval. That interval is not a reason to mark
the requirement passed.

The fitting calculation satisfies its tuning objective. This does not establish
why the test split differs: finite-sample calibration error and distribution
differences remain possible explanations. No cutoff or target was changed using
the test results.

## What the new diagnostic does

`cacheshift.tuning_diagnostics` uses the saved tuning scores from the original
calibration. It verifies the dataset checksum, checks that all score IDs belong
to tuning, and keeps question groups together. It reads dataset IDs, split and
group metadata; it does not use question text, answer labels or test scores.
It needs no model inference, GPU, credentials or network access.

For each of five seeds, it divides the tuning groups into five folds. Each cutoff
is fitted using four folds and evaluated on the remaining fold. Every group is
validated once per seed. A 2,000-resample group bootstrap gives a 95% interval for
each validation share, conditional on that fold's cutoff. No candidate methods
are compared or selected, and the gateway's configuration is not modified.

```powershell
.venv/Scripts/python.exe -m cacheshift.tuning_diagnostics --dataset data/retune_demo/questions.jsonl --calibration experiments/results/retune-20261004/calibration-601.json --output experiments/results/my-tuning-diagnostics.json
```

The output filename must be new. The committed
[report](../../../experiments/results/tuning-diagnostics-20261005.json) contains
all fold assignments, cutoffs, validation estimates, intervals and source hashes.

For seed 601, each fold fits 160 questions and validates 40:

| Validation fold | Strong-model share | Conditional 95% interval |
|---|---:|---:|
| 0 | 40.0% | 25.0–55.0% |
| 1 | 50.0% | 35.0–65.0% |
| 2 | 47.5% | 32.5–62.5% |
| 3 | 65.0% | 50.0–77.5% |
| 4 | 50.0% | 35.0–65.0% |

This illustrates variability within the existing tuning sample. These smaller
folds do not estimate the original test failure's cause or prove that more data
will fix it. Folds overlap in their training data and seeds reuse the same
questions; do not count them as independent research replications. Small or
homogeneous validation samples can also give misleadingly narrow percentile
intervals. Quality and cost are not evaluated by this diagnostic.

## Next experiment, before looking at new test results

1. Declare a larger calibration pool and a separate evaluation pool whose
   question families exclude the exposed 500-question development fixture.
   Document benchmark provenance, grouping, sample sizes and selection rules.
   Access to suitable data and official keys must be established first; no new
   held-out dataset is claimed here.
2. Use only calibration data to assess cutoff stability and any proposed method
   changes. Keep ordinary miss-only quantile calibration as a baseline. Do not
   adjust the target or use a test-set quantile to force a passing share.
3. Freeze the method, cache policy, sample definitions, seeds and the 50% target
   before running the declared evaluation. Report all seeds and failures. Keep
   share, dollar cost and quality separate; the accuracy check still needs
   benchmark keys and an agreed interpretation of the quality requirement.
4. If calibration is still unstable or representative new data is unavailable,
   report the limitation. An adaptive quota controller would change the method
   and its quality tradeoff; it must be evaluated as a separate approach rather
   than substituted silently for score-threshold re-tuning.

The real-request study discussed in the Round 2 review addresses external
validity. A log without official answers can help study score selection, but it
cannot by itself finish #5's answer-quality requirement.
