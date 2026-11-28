"""Robustness of re-tuning at scale: does the verdict hold for other fit/held-out splits?

    python -m cacheshift.retune_splits --run-dir experiments/results/retune-scale-20261127 --splits 20

Added after the first results (not in the protocol). With the cache on, a new cutoff changes only
which model the cache misses go to: the hits, and each miss's router score, are in the cached
run's log. So a re-tuned run can be rebuilt exactly from that log and the recorded answers, for
any cutoff. For each split (SHA-256 of "<salt>:<group>", even = fit half), this fits the cutoff on
the fit half's misses as retune_log does and judges it on the other half, as the report does.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from cacheshift import report
from cacheshift.replay_gateway import STRONG, WEAK, calibrate_scores, load_dataset
from cacheshift.retune_scale import DATASET, TARGET


def in_fit_half(group, salt):
    return int(hashlib.sha256(f"{salt}:{group}".encode("utf-8")).hexdigest(), 16) % 2 == 0


def with_cutoff(events, records, cutoff):
    """The same run with another cutoff. Which requests hit the cache does not change (the cache
    matches on text), but a miss goes where its logged score says, and a later hit serves the answer
    that the matched question got when it missed."""
    out, stored = [], {}
    for event in events:
        if event["cache_hit"]:
            matched = event["matched_question_id"]
            model = stored[matched]
            out.append({**event, "model": model, "answer": records[matched]["answers"][model]["answer"]})
            continue
        route = "strong" if event["router_score"] >= cutoff else "weak"
        model = STRONG if route == "strong" else WEAK
        stored.setdefault(event["question_id"], model)
        answer = records[event["question_id"]]["answers"][model]
        out.append({**event, "route": route, "model": model, "answer": answer["answer"], "cost_usd": answer["cost_usd"]})
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--splits", type=int, default=20)
    parser.add_argument("--samples", type=int, default=2000)
    args = parser.parse_args(argv)
    records = load_dataset(DATASET)
    with gzip.open(args.run_dir / "semantic_0.90.jsonl.gz", "rt", encoding="utf-8") as stream:
        cached = [json.loads(line) for line in stream]
    original = json.loads((args.run_dir / "results.json").read_text())["cutoff"]
    rows = []
    for salt in range(args.splits):
        fit_groups = sorted({records[e["question_id"]]["group_id"] for e in cached
                             if in_fit_half(records[e["question_id"]]["group_id"], salt)})
        fit_set = set(fit_groups)
        scores = [e["router_score"] for e in cached
                  if not e["cache_hit"] and records[e["question_id"]]["group_id"] in fit_set]
        cutoff = calibrate_scores(scores, TARGET)["threshold"]
        after = with_cutoff(cached, records, cutoff)
        x = report.retune_comparison(cached, after, records, {"fit_group_ids": fit_groups, "threshold": cutoff},
                                     TARGET, samples=args.samples)
        rows.append({"salt": salt, "cutoff": cutoff, "verdict": x["after_band_verdict"],
                     "share_before": x["before"]["strong_share_of_routed"],
                     "share_after": x["after"]["strong_share_of_routed"],
                     "accuracy_change": x["change"]["accuracy"], "held_out_groups": x["held_out_groups"]})
        print(f"split {salt:2d}: cutoff {cutoff:.4f}, held-out share {report.pct(x['before']['strong_share_of_routed']['estimate'])}"
              f" -> {report.pct(x['after']['strong_share_of_routed']['estimate'])} "
              f"({report.rng(x['after']['strong_share_of_routed'], report.pct)}), accuracy "
              f"{report.pts(x['change']['accuracy']['estimate'])}: {x['after_band_verdict']}", flush=True)
    verdicts = [row["verdict"] for row in rows]
    summary = {"note": "Added after the first results; not part of the protocol.", "original_cutoff": original,
               "splits": len(rows), "within": verdicts.count("within"),
               "verdicts": {v: verdicts.count(v) for v in sorted(set(verdicts))}, "rows": rows}
    (args.run_dir / "splits.json").write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    print(f"{summary['within']} of {len(rows)} splits: within ±3 points (estimate and whole range)")


if __name__ == "__main__":
    main()
