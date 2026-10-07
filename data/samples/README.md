# Data samples

Small files committed so the project can be developed and reviewed without downloading full datasets. Rebuild them with `python data/load_routerbench.py`.

| File | What it is |
|---|---|
| `routerbench_summary.json` | Row count, column names, models, benchmarks, average score and total cost per model, and the SHA-256 of the downloaded file |
| `routerbench_0shot_sample.csv` | 20 randomly chosen questions (seed 0) with every model's answer, score and cost |

**Source and credit:** RouterBench, Q. J. Hu et al., "RouterBench: A Benchmark for Multi-LLM Routing System," arXiv:2403.12031, 2024. Data from [huggingface.co/datasets/withmartian/routerbench](https://huggingface.co/datasets/withmartian/routerbench) (`routerbench_0shot.pkl`); the authors' code repository [github.com/withmartian/routerbench](https://github.com/withmartian/routerbench) is MIT-licensed. The dataset card states no separate license. We commit only this small sample, with credit; the full file stays out of the repository (`data/raw/`, gitignored).

**Known gap:** RouterBench records whether each model's answer was correct, but not the answer key itself. The test set will add answer keys from the original benchmarks.
