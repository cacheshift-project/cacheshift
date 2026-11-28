"""Uneven repeats: does the cache move the expensive-model share when easy questions repeat more?

    python -m cacheshift.uneven_repeats --run-dir experiments/results/uneven-repeats-<date>

Implements docs/sprints/Sprint_4/Uneven_Repeats_Protocol.md (fixed before any run). For each repeat
policy (uniform, easy-repeat, hard-repeat), the router's cutoff is set on that policy's tuning
stream with no cache (the traffic before a cache is added), then the test stream goes through
ReplayGateway twice, with no cache and with the semantic cache at 0.90. The primary outcome is the
cache's own effect on the expensive-model share for easy-repeat. Recorded answers only.
"""

import argparse
from collections import Counter
import gzip
import hashlib
import json
from pathlib import Path
import random

import numpy as np

from cacheshift import report
from cacheshift.gateway import ROOT
from cacheshift.replay_gateway import calibrate_scores, load_dataset, summarize, validated_score
from cacheshift.retune_scale import DATASET, DATASET_SHA, SCORES, MemoRouter, through_gateway

SEED = 601
THRESHOLD = 0.90
TARGET = 0.5
WEIGHT = 3
POLICIES = ("easy-repeat", "hard-repeat", "uniform")   # primary first


def level(subject):
    if subject.startswith(("elementary_", "high_school_")):
        return "easy"
    if subject.startswith(("college_", "professional_")):
        return "hard"
    return "other"


def weighted_stream(records, policy, seed=SEED, repeat_fraction=0.5):
    """Every question once plus weighted repeats, shuffled (cache_quality.request_stream with weights)."""
    ids = sorted(records)
    favoured = {"easy-repeat": "easy", "hard-repeat": "hard", "uniform": None}[policy]
    weights = [WEIGHT if favoured and level(records[qid]["subject"]) == favoured else 1 for qid in ids]
    rng = random.Random(seed)
    stream = ids + rng.choices(ids, weights=weights, k=round(len(ids) * repeat_fraction / (1 - repeat_fraction)))
    rng.shuffle(stream)
    return stream


def repeats_by_level(stream, records):
    """Extra appearances (beyond the first) of each topic level's questions."""
    counts = Counter(stream)
    out = Counter()
    for qid, count in counts.items():
        out[level(records[qid]["subject"])] += count - 1
    return {name: out[name] for name in ("easy", "hard", "other")}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--scores-from", type=Path,
                        help="A retune_scale run dir: reuse the router scores its no-cache log recorded for the test "
                             "questions (spot-checked against fresh scoring)")
    args = parser.parse_args(argv)
    from cacheshift.router import LocalBERTRouter
    from cacheshift.semantic_cache import EMBEDDING_MODEL, SentenceEmbedder

    digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    if args.dataset == DATASET and digest != DATASET_SHA:
        raise SystemExit("The MMLU set differs from the protocol's; rebuild it with --all-families")
    args.run_dir.mkdir(parents=True, exist_ok=False)
    records = load_dataset(args.dataset)
    split = {name: {qid: row for qid, row in records.items() if row["split"] == name} for name in ("tuning", "test")}
    router = MemoRouter(LocalBERTRouter(ROOT / "data/cache/routellm", offline=True), SCORES)
    if args.scores_from:
        with gzip.open(args.scores_from / "no_cache.jsonl.gz", "rt", encoding="utf-8") as stream:
            logged = {}
            for line in stream:
                event = json.loads(line)
                logged[event["question_id"]] = event["router_score"]
        if set(logged) != set(split["test"]):
            raise SystemExit("That run's no-cache log does not cover exactly this test split")
        for qid in random.Random(SEED).sample(sorted(logged), 20):
            fresh = validated_score(router.router, records[qid]["text"])
            if fresh != logged[qid]:
                raise SystemExit(f"Logged score for {qid} ({logged[qid]}) differs from fresh scoring ({fresh})")
        router.scores.update({records[qid]["text"]: {"router_score": value} for qid, value in logged.items()})
        print(f"Reused {len(logged):,} logged test-question scores (20 spot-checked, identical)", flush=True)
    embed = SentenceEmbedder(EMBEDDING_MODEL, cache_dir=str(ROOT / "data/cache/embeddings"))
    embed.warm(row["text"] for row in split["test"].values())
    score = lambda qid: validated_score(router, records[qid]["text"])

    results = {"protocol": "docs/sprints/Sprint_4/Uneven_Repeats_Protocol.md", "dataset_sha256": digest,
               "weight": WEIGHT, "threshold": THRESHOLD, "policies": {}}
    by_level = {}
    for name in ("easy", "hard", "other"):
        values = [score(qid) for qid, row in split["test"].items() if level(row["subject"]) == name]
        by_level[name] = {"questions": len(values), "mean_router_score": float(np.mean(values))}
    results["router_score_by_level"] = by_level
    print("Mean router score by topic level (test):", {k: round(v["mean_router_score"], 4) for k, v in by_level.items()},
          flush=True)

    for policy in POLICIES:
        tuning_stream = weighted_stream(split["tuning"], policy)
        fitted = calibrate_scores([score(qid) for qid in tuning_stream], TARGET)
        calibration = {"target_strong_share": TARGET, "threshold": fitted["threshold"],
                       "tuning_strong_share": fitted["tuning_strong_share"]}
        stream = weighted_stream(split["test"], policy)
        print(f"{policy}: cutoff {fitted['threshold']:.4f} (tuning-stream share {fitted['tuning_strong_share']:.4f}); "
              f"{len(stream):,} test requests", flush=True)
        common = dict(records=records, router=router, calibration=calibration, digest=digest, stream=stream,
                      run_dir=args.run_dir)
        _, fresh = through_gateway(f"{policy}_no_cache", cache_enabled=False, **common)
        engine, cached = through_gateway(f"{policy}_semantic_{THRESHOLD:.2f}", semantic_threshold=THRESHOLD,
                                         embed=embed, **common)
        built = report.build(cached, records, TARGET, fresh_events=fresh)
        effect = built["paired"]["strong_share_change"]
        fresh_share = built["fresh"]["strong_share_of_routed"]
        results["policies"][policy] = {
            "cutoff": fitted["threshold"], "tuning_stream_share": fitted["tuning_strong_share"],
            "requests": len(stream),
            "repeats_by_level": repeats_by_level(stream, records),
            "cache_effect_on_share": effect, "verdict": report.band_verdict(effect),
            "share_no_cache": fresh_share, "share_cache": built["rates"]["strong_share_of_routed"],
            "drift_cache": built["rates"]["drift_from_plan"],
            "drift_no_cache": {"estimate": fresh_share["estimate"] - TARGET,
                               "ci95": [fresh_share["ci95"][0] - TARGET, fresh_share["ci95"][1] - TARGET]},
            "accuracy_change_vs_fresh": built["paired"]["accuracy_change"],
            "usd_per_1000_cache": built["rates"]["usd_per_1000"], "usd_per_1000_no_cache": built["fresh"]["usd_per_1000"],
            "hit_rate": built["rates"]["hit_rate"],
            "wrong_caused_by_cache": built["totals"]["wrong_question_wrong"],
            "summary_cache": summarize(cached, TARGET), "summary_no_cache": summarize(fresh, TARGET),
            "config_cache": engine.config}
        print(f"  cache effect on share: {report.pts(effect['estimate'])} points ({report.rng(effect, report.pts)}) "
              f"-> {results['policies'][policy]['verdict']}", flush=True)
        (args.run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
        for name in (f"{policy}_no_cache", f"{policy}_semantic_{THRESHOLD:.2f}"):
            path = args.run_dir / f"{name}.jsonl"
            with path.open("rb") as source, gzip.open(path.with_suffix(".jsonl.gz"), "wb", compresslevel=9) as target:
                target.write(source.read())
            path.unlink()


if __name__ == "__main__":
    main()
