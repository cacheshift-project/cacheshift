# Controlled drift correction — 12 October 2026

## Protocol fixed before the new scenario results

This is an explicitly synthetic mechanism test on the previously exposed 3,648
MMLU development questions. It is not a fresh confirmatory holdout or a production
trace. No question, answer label, target or scenario will be selected after seeing
these new results. The earlier uniform-repeat experiment has no drift to fix.

Use the released CPU router and score every question individually, exactly as
the gateway does. Score tuning first and fit cutoffs before scoring test. Preserve
the old batched artifacts; audit their decisions against the new single scores,
including all questions and the old cutoff boundary, not just six example prompts.

Retain the miss-only nearest-attainable-share objective (target 50%, ties prefer
fewer strong calls), but place new cutoffs midway between adjacent score groups.
This explicitly versioned `midgap` rule avoids placing a boundary directly on a
tuning score; it does not guarantee stability across machines or arbitrarily
tiny gaps. Individual scoring is the canonical computation for this experiment.

For each seed 601–605, test three fixed repetition policies with 50% extra repeats:
uniform (negative control), high-score popularity and low-score popularity.
The popularity dividing cutoff is the tuning-miss median, frozen before test.
High-score popularity samples repeats with weight 2 above the cutoff and 1 below;
low-score popularity reverses those weights. Every unique question appears once,
then sampled repeats are shuffled into the stream. The generator deliberately
uses router scores to induce selection bias; it is an engineered stress test,
not evidence that user traffic has that pattern. No gold labels drive popularity.

Fit the original cutoff on the incoming tuning stream; fit the replacement on
tuning cache misses. On the identical test stream compare no cache, exact cache
with the original cutoff, and exact cache with the replacement. Cold unbounded
exact caches only. No quota controller or test-set quantile is used.

For each skew policy and every seed require: cache-on minus cache-off routed
share at least 5 percentage points in magnitude with a paired 95% interval
excluding zero; reduction in absolute target error at least 3 points with a
paired 95% interval above zero; retuned share within 47–53%; and retuned accuracy
inside the no-cache marginal accuracy interval (the issue's descriptive criterion,
not proof of equivalence). Report the uniform control and all failures. Use 2,000
question-family paired bootstrap resamples, conditional on the fitted cutoffs.
Repeated seeds reuse one pool. Costs are historical; no energy/live-latency claim.

The October 5 [Retune_Followup.md](Retune_Followup.md) explains the larger-pool
follow-up. Size, balance and benchmark remain confounded; the ARC failures remain.
Even a passing engineered test leaves real-traffic drift correction unverified.

## Results

Protocol/code commit `cfe2af5` was pushed before this run started. All 15 cutoffs
were frozen before single-question test scoring. Each policy exposes the same
unique tuning-miss pool; the replacement is fit once on that pool, while baseline
fits count all 3,648 incoming tuning requests per policy/seed.

The [full report](../../../experiments/results/controlled-drift-20261012/report.json)
records all scenarios and failures/controls, paired intervals, quality warnings
and raw trace hashes. Both skew cases demonstrate cache-selection drift and
correction across every seed; the uniform negative control does not.

| Repeat policy | Untuned cached strong share | Retuned share | Absolute target-error reduction |
|---|---:|---:|---:|
| Uniform control | 50.49–51.21% | 50.99% | −0.49 to +0.22 points |
| High-score popularity | 41.45–43.75% | 50.99% | 5.26–7.57 points |
| Low-score popularity | 57.13–58.17% | 50.99% | 6.14–7.18 points |

The cache effect is −8.06 to −6.88 points for high popularity and +6.52 to +7.73
points for low popularity. Every skew-case paired cache-effect interval excludes
zero, and every paired target-error-reduction interval is positive. The uniform
cache-effect intervals all include zero. The single-scoring midpoint cutoff is
`0.4552204678522654`; tuning share is exactly 50%, test misses are 930/1,824.

**Quality is a trade-off, not an unconditional success.** Every skew run passes
the issue's marginal-baseline-interval check, but paired accuracy tells more:

| Policy | Paired retuned-minus-untuned accuracy | Paired 95% intervals |
|---|---:|---|
| High-score popularity | +1.37 to +1.65 points | All above zero |
| Low-score popularity | −1.75 to −2.08 points | All below zero |

Thus high-score popularity demonstrates correction with an accuracy improvement;
low-score popularity demonstrates correction with a detectable accuracy loss.
The report explicitly flags all five low-policy loss cases. The original success
criterion was not changed after results; the paired-loss warning is descriptive.
Do not call this quality-preserving across both directions or close #5 on that
claim. A pre-agreed non-inferiority margin and real-traffic evidence remain needed.

## Numerical audit and application

All 3,648 original batch scores were compared with individual scores, using the
checksum-verified old raw trace and calibration. Maximum difference:
`1.8438798726760908e-7`. Four old baseline/seed comparisons changed one tuning
decision each (three distinct questions); no old test decisions changed and no
old retuned-cutoff decisions changed on this laptop. This is an observed result,
not proof that numerical differences can never alter routing.

The new midpoint has a nearest tuning-score distance of `9.5334e-8`; the small
margin still does not guarantee cross-hardware stability. New artifacts require
`scoring_mode=single`, and the gateway uses the same individual scoring. Historical
observed-score artifacts remain readable and unchanged.

The [audit](../../../experiments/results/controlled-drift-20261012/batch-single-audit.json)
and complete paired-score JSONL in the same directory permit independent numerical
checking without the old ignored raw logs. The
[actual gateway application](../../../experiments/results/controlled-applied-20261012/report.json)
loaded this midpoint artifact and returned `B` twice, with routes `strong` then
`cache`, verifying all required log fields. Single scoring and both synthetic
repeat directions used CPU only; no paid model calls or GPU.

## Reproduce

After the CPU router setup, use a new output directory:

```powershell
.venv/Scripts/python.exe -m cacheshift.controlled_drift --run-dir experiments/results/my-controlled-drift
.venv/Scripts/python.exe tools/check_retuned_gateway.py --dataset data/mmlu_retune_20261007/questions.jsonl --calibration experiments/results/my-controlled-drift/calibration.json --run-dir experiments/results/my-controlled-gateway
```

Optional `--audit-old experiments/results/story3-mmlu-20261007` requires the old
local ignored raw trace; fresh clones can instead inspect the committed audit and
complete score pairs. Score JSONs and frozen fits record exactly what was used.

Final verification: 65 Windows tests passed, including source/calibration hash
binding, complete 3,648-question numerical-audit provenance, canonical stage
ordering, midpoint objective/ties, wrong-mode rejection and backward compatibility.
The actual local HTTP application check passed. Raw traces remain ignored; their
checksums are in the report. All source score exports and JSON artifacts use LF.
All 15 baseline fits were independently regenerated from the committed tuning
scores and fixed stream rules, matching the frozen full-input SHA-256 exactly.
The compact frozen-fit export omits duplicated score/ID arrays; the original full
input is kept locally under ignored `raw/` and can be regenerated without inference.
