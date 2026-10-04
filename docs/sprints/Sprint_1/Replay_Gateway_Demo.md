# Replay gateway demo

Issue [#11](https://github.com/cacheshift-project/cacheshift/issues/11) connects the
local RouteLLM BERT router from #10 to recorded model answers and an exact-repeat
cache. Requests pass through a real FastAPI HTTP endpoint. Each successful
request produces a JSONL log entry in the format proposed in `docs/Team_Roles.md`.

## Run the demo

From the repository root, after the [router setup](RouteLLM_Feasibility.md):

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-router.txt
.\.venv\Scripts\python.exe -m cacheshift.demo --run-dir experiments/results/my-first-demo
```

The command starts a temporary HTTP server on a free loopback port, sends the
same 15-request stream without caching and with exact caching, then stops the
server. It prints request routes and the comparison table. Model scoring is
local; answers are historical lookups. There are no paid model API calls.
Use a new output directory for each run. Existing run directories and logs are
never overwritten. Add `--download` only if the router checkpoint is not yet
cached. By default the model is loaded offline.

Outputs:
- `no_cache.jsonl` and `exact_cache.jsonl`: complete per-request logs.
- `report.json`: calibration, stream IDs, configuration, and summary counts.
- `report.md`: the printed comparison in a readable file.

## Run an interactive server

```powershell
.\.venv\Scripts\python.exe -m cacheshift.gateway --run-dir experiments/results/my-server
```

Open `http://127.0.0.1:8000/docs` for the local API interface. `GET /questions`
lists valid test IDs and question text. Submit an ID with `POST /replay`:

```powershell
$requestBody = @{ question_id = 'arc-challenge.test.839' } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8000/replay -ContentType 'application/json' -Body $requestBody
```

Send it again to see `route: cache`, the source model, and zero additional
historical model cost. The first call routes only if that question has not
already been cached in this server session. Stop the server with Ctrl+C.
`GET /config` exposes the configuration ID and threshold.

This endpoint deliberately accepts known original question IDs. Unknown IDs,
tuning IDs, and requests with arbitrary prompt fields are rejected. Rewordings
are not assigned an original model response. This is a replay endpoint, not
the general OpenAI-compatible endpoint or live backend planned in issue #6.

## Data and calibration

The small committed fixture contains 20 original ARC questions with both recorded
answers: ten development tuning questions and ten development test questions.
It follows the handoff fields and explicitly defines each model outcome as
`answer`, `correct`, and `cost_usd`. Keys come from the existing official ARC key
join; the router and cache never consult keys or correctness. This standalone
fixture does not modify or replace Spencer's RouterBench loader branch.

The export is reproducible from the original keyed development fixture:

```powershell
.\.venv\Scripts\python.exe tools/build_replay_demo.py ../data/prepared/arc_500_keyed.jsonl
```

That optional source file exists in Anthony's earlier prototype, not in a fresh
clone. The committed export is sufficient to run the demo. The exporter rejects
a different source checksum. `data/replay_demo/manifest.json` records provenance,
selection, and the output checksum. Groups cannot cross the tuning/test boundary.

The router threshold is chosen using tuning prompts only, aiming for a 50%
strong-model share. If tied scores make the target unattainable, calibration
selects the nearest achievable share and prefers fewer strong calls on a tie.
The actual tuning share is recorded. The threshold stays fixed for both runs.
The test stream is ten originals plus five repeat draws, shuffled with seed 601.

The cache is initially empty, is scoped to one gateway configuration, and uses
the exact question ID and text. Cache hits bypass the router and reuse the same
model answer, including any original mistake. No semantic equivalence is assumed.

## Verified result on 4 October 2026

The [saved run](../../../experiments/results/replay-demo-20261004/report.md) used
real local HTTP requests and the downloaded BERT checkpoint. Calibration sent
five of ten tuning questions to the strong model. In the test stream:

| Mode | Requests | Hits | Routed | Strong calls | Strong share of routed |
|---|---:|---:|---:|---:|---:|
| No cache | 15 | 0 | 15 | 10 | 66.7% |
| Exact cache | 15 | 5 | 10 | 8 | 80.0% |

The no-cache test share already differs from the tuning target. The difference
between the paired runs is the cache comparison; the entire gap from 50% cannot
be attributed to caching. The report also shows strong calls divided by all
requests so that denominators are explicit.

These are descriptive development traces, not a statistically established drift
result. The fixture has prior exposure and possible checkpoint training overlap.
Confidence intervals, five-seed evaluation, semantic caching, held-out research
calibration, live APIs, and re-tuning remain separate work. Exact caching cannot
measure semantic false hits. Historical model costs exclude router/cache overhead;
logged latency measures local routing/replay before the log write, not generation
latency of GPT-4 or Mixtral. No energy measurement is made.

## Validation

Tests cover cache bypass, answer provenance, repeated routing without a cache,
HTTP validation, tuning-only calibration, tied scores, invalid costs, group
leakage, fixture checksums, and protection against overwriting existing logs.
The local checkpoint test inherited from #10 also blocks network connections.

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```
