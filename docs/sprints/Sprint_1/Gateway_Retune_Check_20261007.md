# Gateway and fresh retuning check — 7 October 2026

## Protocol recorded before evaluating new test scores

Keep the existing miss-only quantile calibration, official CPU RouteLLM checkpoint,
50% strong-model target, cold unbounded exact cache, 50% uniformly sampled repeats,
seeds 601–605 and 2,000 paired group-bootstrap resamples. Do not change settings
or select a seed after reading the test result. Report failures as well as passes.

Build a new pool from the verified RouterBench zero-shot file and verified official
ARC keys. Exclude all normalized question stems and official ARC IDs in the exposed
500-question fixture. Use all remaining alignable records with recorded strong and
weak responses; key conflicts are rejected. Group by normalized question stem,
order groups by SHA256(`601:` + stem), and put the first half in tuning and the rest
in test. Choice order variants remain in the same group. Sample sizes follow from
this rule rather than outcomes. No router scores or correctness results select rows.

This is fresh relative to our development fixture, not proof of independence from
the router's original training data or of production behavior. Keep the earlier
53.33% failure in the record. No model API calls or generated answer keys are used.

Acceptance remains the issue's stated checks: routed strong share within 47–53%
and retuned accuracy inside the no-cache accuracy interval, for every reported seed.
The latter is a descriptive requirement, not a statistical equivalence test.

## Gateway acceptance

The same SDK app sends the same prompt and model to two real local HTTP servers;
only the base address changes. The second CacheShift request must hit the exact
cache. Every successful gateway event must contain all fields in `docs/Team_Roles.md`.
This verifies the supported single-turn recorded-answer replay contract, not live
provider forwarding, streaming, arbitrary questions or a semantic cache.

## Reproduce

Install the project development dependencies and the router setup described in
`RouteLLM_Feasibility.md`. The dataset builder additionally requires `pyarrow`.
Run from the repository; output directories must be new.

```powershell
.venv/Scripts/python.exe -m cacheshift.app_demo --run-dir experiments/results/my-gateway-check
.venv/Scripts/python.exe tools/build_retune_holdout.py --source ../data/routerbench/routerbench_0shot.pkl --arc-dir ../data/arc --output data/my-retune-holdout
.venv/Scripts/python.exe -m cacheshift.retune --dataset data/my-retune-holdout/questions.jsonl --run-dir experiments/results/my-fresh-retune
```

The retuning command currently labels every report a development evaluation.
For this run, the builder manifest and protocol above establish the narrower
fresh-relative-to-fixture claim; the generic report label does not claim an
independent research holdout.

## Recorded results

**#6: acceptance demonstrated for the supported replay contract.** The actual
[app report](../../../experiments/results/app-demo-20261007/report.json) and
`direct_recorded_strong.jsonl` / `cacheshift.jsonl` in that directory record two
requests to each local server. Direct replay used the strong model twice;
CacheShift routed the first request and served the second from its exact cache.
Both returned `A)`. All 13 required log fields were present, request IDs were
unique, and the cache hit had zero recorded model cost. The SDK test additionally
exercises a weak-model first answer followed by a cache hit. This is ready for
teammate review; live forwarding remains outside this replay demonstration.

**#5: still fails the share requirement.** The
[manifest](../../../data/retune_holdout_20261007/manifest.json) records 970 rows,
966 families, 485 tuning rows in 483 families, and 485 test rows in 483 families.
No exposed official ARC ID remains; no official ID crosses the new split.
Rebuilding produced the same dataset SHA-256:
`986da3d608c24eac87e3f88cb08a71c1f52d8a50b5a266e30b77916197acc37b`.

The unchanged method fitted a tuning share of 49.90%, threshold
`0.4659435380734295`. On test, it routed 267/485 unique misses to the strong
model: **55.05%**, a **5.05-point** miss against the 50% plan. All seeds fail
the 47–53% requirement; all pass the stated accuracy-interval check.

| Seed | Retuned strong share | Retuned accuracy | No-cache accuracy 95% interval |
|---|---:|---:|---:|
| 601 | 55.05% | 90.00% | 87.09–92.66% |
| 602 | 55.05% | 90.10% | 87.35–92.99% |
| 603 | 55.05% | 91.65% | 89.21–93.87% |
| 604 | 55.05% | 88.97% | 85.70–92.09% |
| 605 | 55.05% | 89.07% | 85.91–92.12% |

The [full report](../../../experiments/results/retune-20261007/report.json)
includes every seed, paired differences, intervals and historical costs. Seeds
reuse one question pool; identical miss-only shares are not independent replications.
Seed 601's share interval is 50.51–59.59%. Neither the observed miss nor this
conditional interval establishes its cause. More calibration questions did not
produce a passing result in this particular split.

No setting was changed after evaluation. These questions are now exposed and
must not become a new confirmatory test for a method developed using these results.
The next #5 experiment needs a separately declared pool and a method developed
on calibration data. A quota controller could enforce a share but would change
the routing method and requires its own quality evaluation.

Validation: 51 tests passed. The new builder tests check family grouping and
independence from input order and answer values. Installing Parquet support made
pandas 3 choose Arrow strings in the loader's synthetic test fixture; that fixture
now explicitly uses the published file's object-string format. The loader's narrow
allowlist was not widened. No paid API calls or GPU were used.
