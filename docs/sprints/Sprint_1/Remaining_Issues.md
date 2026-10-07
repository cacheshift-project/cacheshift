# Gateway, re-tuning, API feasibility and AI review

Implementation and evidence from 2026-10-04. These changes build on PRs #21
and #22. Merge those first, then retarget this PR to main. Teammate review is
required. Issues #14 and #17 are outside this change.

**Update, 2026-10-07:** PRs #21–#24 are merged; #15 is closed. The latest
[gateway and fresh retuning check](Gateway_Retune_Check_20261007.md) demonstrates
#6's replay acceptance and records a new #5 failure (55.05% against 47–53%).
The historical pending statuses below describe the original October 4–5 work;
use the linked check for the current #5/#6 evidence and the final
[AI review log](AI_Review_Log.md) for #15.

## Status against the issues

| Issue | Delivered | Still needed |
|---|---|---|
| #6: app endpoint | A tested Chat Completions replay endpoint, unchanged SDK client, real local HTTP demo and request logs | Teammate review. Compatibility is limited to the replay contract below; arbitrary live prompts are not supported. |
| #5: re-tune | One command fits a cutoff on tuning cache misses, evaluates five seeds, saves an applicable configuration and reports paired confidence intervals | The measured routed share is outside the required 47–53% range. Keep the issue open and validate on a separately declared final dataset. |
| #9: API key | One-call script, local .env configuration, bounded output, no retries, sanitized evidence and mocked success/error tests | Anthony's actual paid call and Spencer's independent laptop run. There was no .env in this checkout; no paid call was made. |
| #15: two-model review | Initial ChatGPT/Codex review, supplied Claude initial critique, ChatGPT Round 2 response, immutable plan reference and merged evaluation correction | Claude's actual cross-review, usable chat links and the final team decision. |

## Setup

Run from the repository with the Python environment used for the local router:

```powershell
.venv/Scripts/python.exe -m pip install -e ".[dev]"
```

The [router setup](RouteLLM_Feasibility.md) is required for demos and evaluation.
They use the already-downloaded CPU checkpoint offline. The API helper and SDK
example need only `pip install -e ".[api]"`; the statistical evaluator additionally
needs `pip install -e ".[evaluation]"`.

## #6: change the app's server address

```powershell
.venv/Scripts/python.exe -m cacheshift.app_demo --run-dir experiments/results/my-app-demo
```

This starts two real loopback HTTP servers in turn: a direct recorded strong-model
baseline and CacheShift. The same `ask(base_url, prompt)` function sends the same
model name and question twice to each server; only the address changes. CacheShift's
second request is a cache hit. The committed [demo report](../../../experiments/results/app-demo-20261004/report.json)
and its two JSONL logs record the actual calls. No live AI provider was contacted.

To use the standalone example:

```powershell
.venv/Scripts/python.exe -m cacheshift.gateway --run-dir experiments/results/my-server
# In a second terminal, using the prompt.txt produced by the demo:
.venv/Scripts/python.exe examples/chat_app.py --base-url http://127.0.0.1:8000/v1 --prompt-file experiments/results/my-app-demo/prompt.txt
```

Supported contract: `POST /v1/chat/completions`, a single text-only `user` message
exactly matching one test question, model `cacheshift` or `gpt-4-1106-preview`,
`stream=false`, `n=1`. Both model names select the router; the returned `model`
identifies the model that actually supplied the recorded answer. The app therefore
opts into routing when its address changes. Token usage is unavailable and returns
null. Unsupported settings, system instructions, multiple turns, streaming and
unknown/ambiguous prompts fail explicitly. The endpoint is a local demonstration
without authentication; the command binds only to loopback.

Response schema checked against the [official Chat Completions reference](https://developers.openai.com/api/reference/python/resources/chat/subresources/completions/methods/create).
This is a supported subset, not a claim of full API compatibility. Successful
requests retain the agreed gateway log fields; rejected requests do not run the
router or enter the experiment's successful-request log.

## #5: fit, evaluate and apply a cutoff

```powershell
.venv/Scripts/python.exe -m cacheshift.retune --dataset data/retune_demo/questions.jsonl --run-dir experiments/results/my-retune
.venv/Scripts/python.exe -m cacheshift.gateway --dataset data/retune_demo/questions.jsonl --calibration experiments/results/my-retune/calibration-601.json --run-dir experiments/results/my-retuned-server
```

Each run directory must be new. The command uses 50% as the planned **share of
cache misses routed to the strong model**, not a guaranteed monetary budget.
Optional `--target` and `--repeat-fraction` values must be chosen before test
evaluation. The miss sample comes from a cold, unbounded exact cache: first
occurrences miss and subsequent identical question IDs/text hit. No semantic
cache, eviction or production traffic is modeled.

For each of seeds 601–605, the original cutoff is fit to the full tuning stream
and the replacement cutoff to its cache misses. The command then freezes both
cutoffs and runs the same test stream in three modes: no cache, cache without
re-tuning, and cache with re-tuning. It never selects a cutoff using test scores
or answer correctness. Ties choose the closest attainable share, preferring fewer
strong calls. Saved calibration files bind to the dataset checksum, model revision
and exact-cache policy, and the server checks them before use.

The committed 500-question development export has 200 tuning questions and 300
test questions, chosen by source order before this run. Each stream adds uniformly
sampled repeats to make half its requests repeats. All unique questions appear,
so exact-cache miss samples and the re-tuned cutoff are identical across seeds;
these seeds are not five independent datasets. Official ARC IDs group duplicate
questions and prevent a group from crossing splits. The [manifest](../../../data/retune_demo/manifest.json)
records provenance and the development-data limitation.

Rebuild from the existing keyed prototype fixture, into a new directory:

```powershell
.venv/Scripts/python.exe tools/build_replay_demo.py ../data/prepared/arc_500_keyed.jsonl --output data/my-retune-fixture --count 500 --tuning-count 200
```

The export itself is committed, so fresh clones do not need the parent prototype.
The source checksum is verified by the builder. No answer key is generated by an AI.

### Interpretation of the actual run

See [the report](../../../experiments/results/retune-20261004/report.json).
For seed 601, the routed strong-model share was:

| Mode | Estimate | 95% interval |
|---|---:|---:|
| No cache | 56.67% | 50.08–63.00% |
| Exact cache, original cutoff | 55.00% | 49.33–60.67% |
| Exact cache, re-tuned cutoff | 53.33% | 47.33–59.33% |

Re-tuned accuracy was 89.00% (95% interval 84.97–93.00%); no-cache accuracy was
89.17% (85.17–93.16%). All five seeds satisfy the issue's baseline-accuracy-interval
check, but all fail its ±3-point share check. The share misses by 3.33 points.
Do not change the cutoff, split or target after seeing this result to manufacture
a pass. A future method must be developed on tuning data and evaluated on a newly
declared test set. Being inside a baseline CI is not a statistical equivalence test.

Intervals use 2,000 paired bootstrap resamples of question groups from completed
traces, retaining repeat dependence. They are conditional on fitted cutoffs and
exclude tuning uncertainty. The report also includes cache-on minus cache-off and
retuned minus untuned differences, strong share of all requests, accuracy and
historical dollars per 1,000 requests. Costs exclude CPU/cache overhead. Energy
was not measured; replay latency is not model latency. This does not establish
performance on unseen tasks, semantic matches or production traffic.

Raw logs remain locally under the run's ignored `raw/` directory; their checksums
are in the committed report. Re-running produces new request IDs and timestamps,
so raw hashes differ even when deterministic decisions and summary results agree.

## #9: one real API call on each laptop

Copy `.env.example` to `.env`, then privately fill `OPENAI_API_KEY` and
`OPENAI_MODEL` with a Chat Completions model your account can access. Choose a
model that can give a short text response within the 32-token output cap.

```powershell
.venv/Scripts/python.exe scripts/check_api.py --output experiments/results/api-anthony.json
```

The script sends only “Reply with OK.” to the official OpenAI endpoint, with no
automatic retries. A real call can incur a small provider charge. It prints only
success metadata and token usage, never the key. Errors omit provider response
bodies. `--env` can point to another local .env; do not upload it. Spencer must run
the same command with his own .env and a different evidence filename. Mocked tests
verify the request path and error behavior but do not prove either person's key.

## #15: finish the review

Update, 2026-10-05: the supplied Claude initial critique and ChatGPT Round 2 response
are now preserved in the review log. Claude's cross-review and usable chat links
remain pending. For the tuning-only investigation of #5, see
[re-tuning follow-up](Retune_Followup.md); no routing setting or acceptance status
was changed.

The [AI review log](AI_Review_Log.md) contains the actual ChatGPT/Codex critique and
Claude handoff instructions. The only sprint-plan change in this PR corrects the
evaluation baseline and defines paired comparisons. Unrelated target-user and
team-administration TODOs remain for #14 and #17.
