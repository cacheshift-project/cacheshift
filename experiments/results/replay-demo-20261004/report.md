# Replay gateway demo

Development diagnostic only; no paid model calls.

The planned strong-model share is 50% of requests reaching the router.

| Mode | Requests | Cache hits | Routed | Strong calls | Strong share of routed | Strong share of all | Historical model cost USD |
|---|---:|---:|---:|---:|---:|---:|---:|
| no_cache | 15 | 0 | 15 | 10 | 66.7% | 66.7% | 0.008388 |
| exact_cache | 15 | 5 | 10 | 8 | 80.0% | 53.3% | 0.006699 |

Costs are recorded historical estimates and exclude CPU/cache overhead. Latencies in logs measure local replay, not model generation.

These fixed development traces have no confidence intervals and establish no general drift or quality result. Exact caching cannot test semantic false hits. No retuning is performed.
