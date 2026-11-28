# CacheShift

**A money-saving gateway for AI apps that checks whether the savings are quietly hurting answer quality.**

Many apps cut their AI bill with two tricks: a **semantic cache**, which reuses a stored answer when a new question means the same thing, and a **router**, which sends easy questions to a cheap model and hard ones to an expensive one. Used together, they interfere with each other:

- **The router drifts off its budget.** A router is tuned so that a planned share of questions (say 50%) goes to the expensive model. Once a cache answers the repeat questions first, the router sees a different mix, and the real share can drift from the plan (on our traffic it drifted only 1–2 points: see Status).
- **The cache repeats mistakes.** If the cheap model answered a question wrong, the cache hands that wrong answer to everyone who asks it again in different words.

CacheShift is a gateway (cache → router → models) that measures both problems, reports cost and answer quality side by side with margins of error, and re-tunes the router with one command.

> Boston University · EC601 Product Design in ECE · Fall 2026 · Spencer Aldrich and Anthony Capraru

## Status (27 Nov 2026, before the 4 Dec poster session)

The gateway runs end to end: semantic cache → router → recorded answers, a request log, and a one-page report. There's also a live dashboard and a tool that recommends a safe cache setting. The answers to the proposal's questions:

1. **Drift: small on our traffic.** On 777k real LMSYS prompts the cache moved the expensive-model share +2.2 points [+0.3, +4.1] (Sprint 2). On 13,750 MMLU requests it moved it +1.3 [+0.6, +1.9]. Making easy or hard topics repeat 3× as often kept it within ±3 (Sprint 4). So the headline "caching breaks routing budgets" was dropped, and CacheShift became a measurement tool.
2. **Wrong cached answers depend on the questions.** At 0.90 the cache caused no wrong answers on ARC. On MMLU it caused 4.1% (567 of 13,750), mostly in questions sharing a long template or passage. The **difference check** (compare only the words that differ) cut that by 88% to 0.49%.
3. **Re-tuning works with enough traffic.** It returns the share to 50.2% [48.6, 52.0] on questions it wasn't fitted to, costing 0.15 points of accuracy. It holds in 16 of 20 random splits. On 970 requests it couldn't be told apart from noise.
4. **Energy:** measured once on an SCC L40S GPU (Sprint 2): 4-bit Llama-3.1-8B used 3.59 J/token vs 6.28 for bf16.

Details: [Sprint 4 results](docs/sprints/Sprint_4/Sprint4_Experiment_Results.md), [Sprint 3](docs/sprints/Sprint_3/README.md), [Sprint 2](docs/sprints/Sprint_2/README.md). The proposal was approved on 23 Sep 2026 ([`docs/proposal/`](docs/proposal/)).

**Commands:**
- Report: `python -m cacheshift.report`
- Safe setting finder: `python -m cacheshift.setting_finder`
- Re-tuning: `python -m cacheshift.retune_log`
- Live demo: see below.

## Repository layout

```
cacheshift/
├── src/cacheshift/     The gateway: cache, router, model connections, logging
├── data/               Test-set building scripts and small data files (large raw data is not committed)
├── experiments/        Experiment configs and the scripts that run them
├── tests/              Automated tests, run on every pull request
├── docs/
│   ├── Team_Roles.md   Who owns what, and the two handoff formats
│   ├── proposal/       The submitted proposal and its source
│   ├── sprints/        One folder per sprint: goal, stories, demo, retro
│   └── poster/         Final poster
└── tools/              Helper scripts (e.g., building .docx files from markdown)
```

## Getting started

Requires Python 3.12.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pytest
```

API keys go in a `.env` file (copy `.env.example`). **Never commit `.env`.** It is already in `.gitignore`.

## Live demo dashboard

Watch questions go through the gateway one at a time: which ones the cache answers, which go to the cheap or the expensive model, when the cache gives a question another question's answer, and running cost, accuracy and expensive-model share against the plan. It uses recorded answers, so no API key or internet is needed once the models are downloaded.

```bash
pip install --index-url https://download.pytorch.org/whl/cpu torch   # CPU PyTorch, once
pip install -r requirements-router.txt -e ".[cache]"
python -m cacheshift.dashboard --download   # first time only: downloads the router and the similarity model
python -m cacheshift.dashboard              # after that, works offline
```

Open http://127.0.0.1:8050. Pick a match setting (No cache, 0.95, 0.90 or 0.80), then **Start**, or **Next question** to go one at a time (Space and → also work). Loading takes about a minute on a laptop. Each run's request log is saved in `experiments/results/dashboard-runs/`, and **Open the one-page report** makes the report (#48) from it.

**Difference check** (Sprint 4): the button next to the match setting turns on the fix for questions that share long text. **Runs compared**, under the meters, keeps one row per run so settings can be shown side by side (for example 0.90, then 0.90 with the check, on the MMLU set).

**Kiosk mode** for the poster table: open http://127.0.0.1:8050/?play=normal&loop=1 (optionally `&setting=0.80` and `&check=1`) and it plays by itself and starts over at the end.

To show the template problem from the Sprint 4 results, start it on MMLU: `python -m cacheshift.dashboard --dataset data/mmlu_all_20261127/questions.jsonl` (build that set first, see `docs/sprints/Sprint_4/Sprint4_Experiment_Results.md`). At 0.90, "moral scenarios" and shared-passage history questions get each other's answers.

For the poster: at **0.80**, questions 484 and 493 of the stream get another question's answer. Run on **Fast** to about 480, then step through with **Next question**.

## How we work

For the app-compatible replay endpoint, re-tuning command, API check and their
current acceptance status, see [remaining issue work](docs/sprints/Sprint_1/Remaining_Issues.md).

For the end-to-end replay gateway and its local HTTP demo (issue #11), see
[`Replay gateway demo`](docs/sprints/Sprint_1/Replay_Gateway_Demo.md).

For the local CPU router smoke test (issue #10), see
[`RouteLLM feasibility`](docs/sprints/Sprint_1/RouteLLM_Feasibility.md).
It scores ten committed development questions without paid model calls.

See [`CONTRIBUTING.md`](CONTRIBUTING.md) and [`docs/Team_Roles.md`](docs/Team_Roles.md). In short: every change goes through a branch and a pull request, tests must pass, and the other teammate reviews before merging.

## Research questions (from the proposal)

1. **Drift:** how far does a cache push a budget-tuned router off its planned share, cost, and answer quality?
2. **Wrong cached answers:** how often is a cached answer wrong for the new question (false hits vs. inherited errors)?
3. **Re-tuning:** does re-setting the router on the questions the cache didn't answer restore the plan?
4. **Energy (stretch):** does measured energy per token change which model the router should pick?
