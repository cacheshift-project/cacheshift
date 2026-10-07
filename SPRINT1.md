# SPRINT1.md — CacheShift: plan for the first two weeks

*Spencer Aldrich and Anthony Capraru · Sprint 1: 28 Sep – 12 Oct 2026, demo 13–14 Oct · Board: [CacheShift project board](https://github.com/orgs/cacheshift-project/projects/1/views/1) · Team rules: [`TEAM.md`](TEAM.md)*

## 1. Mission (best guess, not final)

For **engineers who run an LLM feature under a monthly budget, with a cache in front of a model router**, CacheShift is a **gateway and measurement tool** that **shows how the cache shifts the router's cost and answer quality, and re-tunes the router for the questions it actually sees**. Unlike **gateway dashboards that only show how often the cache is used and how much it saves**, it **shows how good the cached answers are and how far the router has drifted from its budget, with margins of error.**

## 2. Target user

**Not named yet, and this is our biggest gap: we have not contacted anyone.** Profile: an engineer who runs an LLM feature with a cache and a router under a budget. Our first three messages go out by 9 Oct (a BU team running an AI service, an open-source gateway maintainer, an industry engineer); we name one person here once they agree to talk. Backup: Spencer's own K-12 assessment LLM service, though a teammate is a biased user.

## 3. User stories (each is an issue on the board)

| # | Story | Done when | Owner |
|---|---|---|---|
| 1 | **See the drift.** As the engineer, I want to see how far my router's strong-model share, cost and accuracy change once the cache is on, so I know whether my cost/quality trade-off is still where I set it. | For 3 budgets × 5 cache settings × 3 repetition rates: planned vs. real share, cost per 1,000 questions and accuracy, each with a 95% CI | Spencer |
| 2 | **Know what a cached answer costs in quality.** As the engineer, I want every cached answer checked against the correct answer, so I know whether savings come out of quality. | False hits and inherited errors per cache setting; a hand check of 50 cached answers agrees with the automatic labels ≥ 90% | Spencer |
| 3 | **Fix the drift.** As the engineer, I want one command that re-tunes the router on the questions that get past the cache, so my real share returns to my plan. | On the test split, real share within ±3 points of plan; accuracy within the no-cache margin | Anthony |
| 4 | **Use it on my app.** As the engineer, I want to point my app at the gateway instead of the AI provider, so I get the savings and the report without changing my code. | An example app switches by changing one web address; the gateway writes a valid request log | Anthony |
| 5 | **Trust the test set.** As a researcher, I want reworded questions with human-written correct answers, so results don't depend on an AI grading itself. | Answers only from benchmark keys; ≥ 95% of 100 hand-checked rewordings keep their meaning; one-command rebuild | Spencer |

## 4. Feasibility — what we have proven

- **Data: RouterBench (11 models' recorded answers, scores, costs).** **Done:** `data/load_routerbench.py` downloads and safety-checks it: 36,497 questions, 11 models (GPT-4 avg. score 0.78; Mixtral 0.55); 20-question sample committed. **Gap:** no answer keys; ARC keys joined for 500 questions so far.
- **Router: RouteLLM's released routers.** **Done:** `python -m cacheshift.score_router` scores 10 questions on CPU with the BERT router, no GPU or API key ([notes](docs/sprints/Sprint_1/RouteLLM_Feasibility.md)).
- **API keys (OpenAI and/or Anthropic) for live mode and the rewording check.** **Not yet:** `scripts/check_api.py` is tested with mocked calls only (#9); the replay demo does not need it.
- **Repo runs on a second machine.** **Done:** fresh install and `pytest` pass on Spencer's Mac and Anthony's Windows laptop.
- **GPU (energy stretch goal only).** BU shared GPU access requested; not needed for the minimum project.

## 5. Tooling

- **Python 3.12:** we both know it, and the ML tools are Python (free; laptops)
- **FastAPI + uvicorn:** serve the gateway's OpenAI-style endpoint (free; laptops)
- **RouteLLM BERT router (PyTorch, Transformers):** the router our proposal studies; its tuning code causes the drift (free, 1.1 GB download; laptop CPU)
- **sentence-transformers:** semantic-cache embeddings without a paid API (free; laptop CPU)
- **Python standard library, `certifi`:** download and safety-check RouterBench (free; laptops)
- **pandas, NumPy:** data handling, metrics and bootstrap confidence intervals (free; laptops)
- **OpenAI / Anthropic APIs:** live mode and the ~200-question rewording check (pay per token, team cap $100, tentative; cloud)
- **pytest + GitHub Actions:** tests run on every pull request (free at our usage; GitHub)
- **vLLM on the BU shared GPU:** stretch goal, energy per token (free to us; BU cluster)

## 6. Demo sentence

**At the end of two weeks we will show a stream of test questions flowing through the gateway in replay mode (cache → router → recorded answer) end to end, finishing with a printed report of the planned vs. actual share of questions sent to the strong model.**

## 7. Riskiest assumption and its test

- **A1:** Engineers put a cache in front of a budget-tuned router and would use a drift report. *If wrong:* no user, so nothing anyone adopts.
- **A2:** The drift is real: the questions a cache answers are not a fair sample of the router's scores. *If wrong:* the main finding is "no effect".
- **A3:** A model that answers a question right also answers its rewording right (so replay mode is valid). *If wrong:* experiments need paid live calls.
- **A4:** Routers are tuned to a budget percentile. **Verified** in RouteLLM's tuning code.

**Riskiest: A1:** without a user, nothing else matters. **Cheapest test:** three 15-minute conversations around a mock-up of the drift report. **A2, in two parts** (changed after the AI review): a controlled exact-cache experiment tests the mechanism; a real-traffic check (router scores and lengths of repeated vs. one-off prompts in LMSYS-Chat-1M) tests whether it matters.

**Pivot line:** We change direction if, by the end of Sprint 2, none of the three conversations produces someone who commits to trying a drift and cached-answer-quality report on a sample of their own traffic; saying they would use it is not enough. If only A2 fails, we continue as a measurement study and say so.

**Result this sprint:** A2, controlled part: with an exact cache and random repeats, the cache moved the strong-model share by −1.7 to +2.2 points over five seeds, every 95% CI including zero (300 ARC questions). As both AI reviews predicted, random repeats give no drift; the real-traffic check decides A2. A1: not tested yet (no conversations so far).

## 8. Evaluation and baseline

| We measure | Metric | Compared against |
|---|---|---|
| Drift | Real minus planned strong-model share (points), cost per 1,000 questions, accuracy | The same router **without the cache** (its measured share, not the plan) |
| Wrong cached answers | False-hit rate and inherited-error rate per cache setting | Accuracy of fresh answers to the same questions (no cache) |
| The fix | Share gap and accuracy after re-tuning | Cache + router **without re-tuning** |

- **Data:** held-out RouterBench questions and rewordings (rewordings stay in their question's split); 95% bootstrap CIs by question group; five seeds.
- **Share** = strong calls ÷ requests reaching the router. We also report strong calls ÷ all requests, and dollars per 1,000 incoming questions.
- **Paired:** cache-on minus cache-off on the same question stream and seed, since the no-cache router may already miss its plan. Cutoffs are fit on tuning data only and frozen before testing.
- **Extra baselines:** random removal of the same number of questions, plain recalibration, and no-cache at matched spend. The accuracy margin and the smallest drift that counts are fixed in advance.

## 9. Related work

- **RouteLLM (Ong et al., ICLR 2025):** Learned strong/weak router; cutoff set as a percentile of a fixed sample → **No cache; its docs warn the real share will differ from plan**
- **RouterBench (Hu et al., 2024):** 405,467 recorded answers from 11 models; AIQ metric; Zero-router baseline → **No cache; routers barely beat the Zero router**
- **FrugalGPT (Chen et al., TMLR 2024):** Cascade: cheap model first, escalate if a scorer rejects it → **No cache; pays for the cheap attempt**
- **GPTCache (Bang, NLP-OSS 2023):** Open-source semantic cache; 2–10× faster on hits → **No router; no measure of wrong answers**
- **vCache (Schroeder et al., ICLR 2026):** Learns per-question thresholds to bound the cache's error rate → **No router behind the cache**
- **Zhu et al. (NeurIPS 2023):** Tunes a cache and a model selector together → **Assumes a perfect cache: no false hits, no drift**
- **LLMBridge (Martin et al., 2024):** Working proxy with caching and model selection → **Parts tested separately; interaction not measured**
- **RequestRouter (Sunesh et al., LOCO 2026):** Picks a compressed model per request using measured energy → **No cache, API models or dollars**

Full references: [`docs/proposal/`](docs/proposal/).

## 10. Harm

- **Who gets hurt if it's wrong:** app users given wrong cached answers nobody notices, and the engineer who trusts our report.
- **Worst realistic misuse:** a favourable CacheShift number used to justify aggressive caching that hides a quality drop.
- **How we limit it:** margins of error on every number, quality never blended with cost, claims limited to what we tested.
