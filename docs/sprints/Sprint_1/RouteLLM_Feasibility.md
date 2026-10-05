# Local RouteLLM feasibility

Issue: [#10](https://github.com/cacheshift-project/cacheshift/issues/10).

We selected RouteLLM's released `routellm/bert` checkpoint for the first CPU
gateway prototype. Its tokenizer and classifier run locally after a one-time
download of approximately 1.1 GB of model weights. No GPU or API key is needed.
The weights stay in ignored `data/cache/`; they are not committed.

## Why this router

The official matrix-factorization router uses OpenAI embeddings in its supplied
implementation. The BERT router instead has a local tokenizer and classifier.
This makes BERT suitable for the no-paid-API feasibility requirement. It is a
larger download than the matrix-factorization head, so this choice does not
establish that it is the fastest or best router for the final project.

Our small adapter loads the official checkpoint through Transformers. It does
not install RouteLLM's controller or its unrelated serving dependencies. It
follows the upstream BERT score: the softmax probability of label 0, equivalent
to one minus the combined tie and weak-win probabilities. Higher scores favor
the strong model. The adapter explicitly uses CPU, evaluation mode, inference
mode, and a 512-token limit; truncation is recorded in the output.

Pinned checkpoint: `874d4aa9758c88ff6a71c6c469fba88e42248304`.

Sources:
- [Official checkpoint](https://huggingface.co/routellm/bert/tree/874d4aa9758c88ff6a71c6c469fba88e42248304)
- [Official router implementation](https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/routers/routers.py)
- [Official matrix-factorization implementation](https://github.com/lm-sys/RouteLLM/blob/0b64fdafe049e596a3f5657c219329f24af24198/routellm/routers/matrix_factorization/model.py)

## Reproduce on Windows

From the repository root, using Python 3.12 or later:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install "torch>=2.6,<3" --index-url https://download.pytorch.org/whl/cpu
.\.venv\Scripts\python.exe -m pip install -r requirements-router.txt
.\.venv\Scripts\python.exe -m cacheshift.score_router
.\.venv\Scripts\python.exe -m cacheshift.score_router --offline --output experiments/results/router_smoke_offline.json
.\.venv\Scripts\python.exe -m pytest -q
```

For macOS or Linux, use `.venv/bin/python` and the appropriate official PyTorch
installation command. Those platforms have not been verified by this test.
The first scoring run needs internet access to download the checkpoint. Offline
mode fails if the weights are missing; it never substitutes random scores.

The script prints each question ID and score and saves JSON with the model
revision, input checksum, package versions, token counts, and individual timings.
Use `--input` for another JSONL containing `question_id` and `text`; only `text`
is passed to the model. Duplicate IDs and empty input are rejected.

## Verified run on 4 October 2026

Anthony's Windows laptop scored all ten questions on CPU. An offline rerun
produced identical scores with no truncated inputs. The committed
[`offline report`](../../../experiments/results/router_smoke_offline.json)
contains all ten outputs and exact package versions. The initial
[`download-enabled report`](../../../experiments/results/router_smoke.json)
is included for comparison. These are execution records, not final results.

All nine tests passed locally, including a real-checkpoint test that rejects
socket connections and verifies repeatable inference. CI without the downloaded
weights runs the eight lightweight tests and skips that optional integration
test. Tested versions include Python 3.12.14, CPU PyTorch 2.14.1, and
Transformers 4.57.6.

## Limitations

The ten questions are the first ten rows of our existing ARC development
fixture, selected without consulting model outcomes. The committed input strips
all answers, costs, correctness labels, and reference keys. Its manifest records
the source and checksums. This fixture is independent of Spencer's in-progress
RouterBench loader and does not replace the agreed test-set handoff.

This is a deterministic execution check, not an accuracy estimate, a speed
benchmark, or a budget-calibration experiment. Individual scores and timings
do not have research confidence intervals. No claim about generalization or
the final project's cost savings follows from ten scores. In particular, a
score cutoff of 0.5 does not guarantee that half of requests select the strong
model. Held-out budget calibration and five-seed experiments remain later work.

The selected checkpoint's training data may overlap benchmark material. These
questions must not be presented as an uncontaminated evaluation set. Before
research runs, review training-data overlap and keep tuning/test groups fixed.
