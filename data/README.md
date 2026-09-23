# Data

The test set: benchmark questions with human-written correct answers, groups of rewordings, and question streams with controlled repetition.

- Scripts that download and build the test set are committed here.
- Downloaded and generated data goes in `data/raw/` and `data/cache/`, which are not committed. Anyone can rebuild them from the scripts.
- Small, final files that other code depends on may be committed if they are under a few MB.

Rule: correct answers come only from the benchmarks' answer keys, never from an AI.
