# CacheShift

**A money-saving gateway for AI apps that checks whether the savings are quietly hurting answer quality.**

Many apps cut their AI bill with two tricks: a **semantic cache**, which reuses a stored answer when a new question means the same thing, and a **router**, which sends easy questions to a cheap model and hard ones to an expensive one. Used together, they interfere with each other:

- **The router drifts off its budget.** A router is tuned so that a planned share of questions (say 50%) goes to the expensive model. Once a cache answers the repeat questions first, the router sees a different mix, and the real share can drift far from the plan.
- **The cache repeats mistakes.** If the cheap model answered a question wrong, the cache hands that wrong answer to everyone who asks it again in different words.

CacheShift is a gateway (cache → router → models) that measures both problems, reports cost and answer quality side by side with margins of error, and re-tunes the router with one command.

> Boston University · EC601 Product Design in ECE · Fall 2026 · Spencer Aldrich and Anthony Capraru

## Status

Proposal submitted 22 Sep 2026 and approved 23 Sep ([`docs/proposal/`](docs/proposal/)). Sprint 1 (planning) started 28 Sep.

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
