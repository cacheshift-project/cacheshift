# Experiments

One folder or config per experiment. Each experiment changes **one setting** and records:

- the exact config (budget, cache threshold, repetition rate, seed),
- the code version (git commit),
- results with 95% confidence intervals.

Raw outputs go in `experiments/results/raw/` (not committed); summary tables and plots are committed.
