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
