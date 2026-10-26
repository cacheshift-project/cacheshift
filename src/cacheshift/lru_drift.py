"""Issue #37 / #5: re-tuning under a size-limited (LRU) exact cache, where the questions
reaching the router depend on traffic instead of being fixed by design.

Why: with the cold, never-evicting cache of the controlled study, every question misses
exactly once, so the re-tuned share (50.99%) was guaranteed by construction (#29). With
an LRU cache, popular questions stay cached and unpopular ones keep missing, so the miss
mix moves with the repeat policy.

Protocol (docs/sprints/Sprint_2/LRU_Retune_Protocol.md, proposed in #37):
- Committed single-question router scores and pool from controlled-drift-20261012; no new
  router inference, so every score is fixed before this experiment exists.
- Capacities: 10% and 25% of the unique questions in a split. Seeds 601-605.
- Untuned cutoff: fit on every incoming tuning request (no cache). Re-tuned cutoff: fit on
  the tuning requests that miss the LRU cache (repeated misses count each time). Both use
  the midgap rule and are fixed before the test stream is generated.
- No-shift arms (uniform/high/low in tuning and test) decide #5. Shift arms (tune
  uniform, test high or low) are reported descriptively.
- Pass for one run: re-tuned share of routed requests within 47-53%, and the paired 95%
  CI for re-tuned minus untuned accuracy has a lower bound above -1.0 point.
"""

import argparse
import hashlib
import json
from pathlib import Path

from cacheshift.controlled_drift import FixedRouter, POLICIES, error_reduction, stream
from cacheshift.gateway import ROOT
from cacheshift.replay_gateway import ReplayGateway, calibrate_midgap, load_dataset
from cacheshift.retune import SEEDS, paired_report
from cacheshift.router import REVISION

CAPACITY_FRACTIONS = (0.10, 0.25)
NO_SHIFT_ARMS = tuple((policy, policy) for policy in POLICIES)
SHIFT_ARMS = (("uniform", "high"), ("uniform", "low"))
TARGET = 0.5
SHARE_TOLERANCE = 0.03
ACCURACY_MARGIN = -0.010  # proportion: -1.0 percentage point
DEFAULT_SCORES = ROOT / "experiments/results/controlled-drift-20261012"
DEFAULT_DATASET = ROOT / "data/mmlu_retune_20261007/questions.jsonl"
PROTOCOL = ROOT / "docs/sprints/Sprint_2/LRU_Retune_Protocol.md"


def lru_misses(requests, capacity):
    """Requests that miss an initially empty LRU cache of `capacity` entries, in order.

    Same rule as ReplayGateway(cache_capacity=...): a hit refreshes the entry; a miss
    inserts it and evicts the least recently used entry when over capacity.
    """
    if isinstance(capacity, bool) or not isinstance(capacity, int) or capacity < 1:
        raise ValueError("capacity must be a positive integer")
    cache, misses = {}, []
    for key in requests:
        if key in cache:
            cache[key] = cache.pop(key)  # move to most-recent position
            continue
        misses.append(key)
        cache[key] = True
        if len(cache) > capacity:
            del cache[next(iter(cache))]
    return misses


def capacity_for(records, split, fraction):
    unique = sum(row["split"] == split for row in records.values())
    return max(1, round(unique * fraction))


def load_scores(scores_dir, digest):
    scores = {}
    for split in ("tuning", "test"):
        artifact = json.loads((Path(scores_dir) / f"scores-{split}.json").read_text(encoding="utf-8"))
        if (artifact.get("dataset_sha256") != digest or artifact.get("scoring_mode") != "single"
                or artifact.get("split") != split or artifact.get("router_revision") != REVISION):
            raise ValueError(f"scores-{split}.json does not match this dataset, router or scoring mode")
        scores.update(artifact["scores"])
    return scores


def checks(stats):
    share = stats["cache_retuned"]["strong_share_of_routed"]["estimate"]
    accuracy_low = stats["paired_differences"]["retune_effect"]["accuracy"]["ci95"][0]
    result = {"share_within_47_53": abs(share - TARGET) <= SHARE_TOLERANCE + 1e-12,
              "retune_accuracy_ci_lower_above_minus_1pt": accuracy_low > ACCURACY_MARGIN}
    result["passes"] = all(result.values())
    return result


def run_one(records, router, scores, capacity, tune_policy, test_policy, seed, popularity_cutoff,
            output, digest, samples):
    tuning_stream = stream(records, scores, "tuning", seed, tune_policy, popularity_cutoff)
    untuned = calibrate_midgap([scores[qid] for qid in tuning_stream], TARGET)
    misses = lru_misses(tuning_stream, capacity)
    retuned = calibrate_midgap([scores[qid] for qid in misses], TARGET)
    # Both cutoffs are fixed before the test stream is drawn.
    test_stream = stream(records, scores, "test", seed, test_policy, popularity_cutoff)
    events, hashes = {}, {}
    for name, calibration, cache in (("no_cache", untuned, False), ("cache_untuned", untuned, True),
                                     ("cache_retuned", retuned, True)):
        path = output / "raw" / f"cap{capacity}-{tune_policy}-{test_policy}-{seed}-{name}.jsonl"
        engine = ReplayGateway(records, router, calibration, path, cache_enabled=cache,
                               dataset_sha256=digest, router_revision=REVISION, seed=seed,
                               repeats=len(test_stream) - len(set(test_stream)),
                               cache_capacity=capacity if cache else None)
        events[name] = [engine.answer(qid) for qid in test_stream]
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    stats = paired_report(events, records, seed, samples)
    hits = sum(event["cache_hit"] for event in events["cache_retuned"])
    return {"capacity": capacity, "tune_policy": tune_policy, "test_policy": test_policy, "seed": seed,
            "arm": "no_shift" if tune_policy == test_policy else "shift",
            "untuned_threshold": untuned["threshold"], "retuned_threshold": retuned["threshold"],
            "tuning_requests": len(tuning_stream), "tuning_misses": len(misses),
            "test_requests": len(test_stream), "test_hit_rate": hits / len(test_stream),
            "metrics": stats, "absolute_target_error_reduction": error_reduction(events, records, seed, samples=samples),
            "checks": checks(stats), "trace_sha256": hashes}


def run(records, scores, output, digest, samples=2000, seeds=SEEDS, fractions=CAPACITY_FRACTIONS,
        arms=NO_SHIFT_ARMS + SHIFT_ARMS, protocol=PROTOCOL):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    router = FixedRouter(records, scores)
    tuning_unique = sorted(qid for qid, row in records.items() if row["split"] == "tuning")
    # Popularity split point: the cold-cache (unique-question) tuning cutoff, as in the controlled study.
    popularity_cutoff = calibrate_midgap([scores[qid] for qid in tuning_unique], TARGET)["threshold"]
    protocol = Path(protocol)
    report = {"scope": "Re-tuning under a size-limited LRU exact cache (#37/#5); synthetic repeat policies "
                       "on the exposed MMLU development pool, not real traffic",
              "dataset_sha256": digest, "router_revision": REVISION, "scoring_mode": "single",
              "protocol_file": protocol.name if protocol.is_file() else None,
              "protocol_sha256": hashlib.sha256(protocol.read_bytes()).hexdigest() if protocol.is_file() else None,
              "target": TARGET, "share_tolerance": SHARE_TOLERANCE, "accuracy_margin": ACCURACY_MARGIN,
              "capacity_fractions": list(fractions), "popularity_cutoff": popularity_cutoff,
              "threshold_rule": "midgap", "bootstrap_samples": samples, "seeds": list(seeds),
              "runs": []}
    for fraction in fractions:
        capacity = capacity_for(records, "tuning", fraction)
        if capacity != capacity_for(records, "test", fraction):
            raise ValueError("Tuning and test splits must have the same number of unique questions")
        for tune_policy, test_policy in arms:
            for seed in seeds:
                row = run_one(records, router, scores, capacity, tune_policy, test_policy, seed,
                              popularity_cutoff, output, digest, samples)
                report["runs"].append(row)
                print(f"cap {capacity} {tune_policy}->{test_policy} seed {seed}: "
                      f"share {row['metrics']['cache_retuned']['strong_share_of_routed']['estimate']:.4f} "
                      f"{row['checks']}", flush=True)
    decisive = [row for row in report["runs"] if row["arm"] == "no_shift"]
    report["issue_5_passes"] = bool(decisive) and all(row["checks"]["passes"] for row in decisive)
    report["failures"] = [{key: row[key] for key in ("capacity", "tune_policy", "test_policy", "seed", "checks")}
                          for row in report["runs"] if not row["checks"]["passes"]]
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8", newline="\n")
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=DEFAULT_DATASET)
    parser.add_argument("--scores-dir", type=Path, default=DEFAULT_SCORES)
    args = parser.parse_args(argv)
    records = load_dataset(args.dataset)
    digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    report = run(records, load_scores(args.scores_dir, digest), args.run_dir, digest)
    print("Issue #5 decisive (no-shift) runs all pass:", report["issue_5_passes"])
    print("Runs that did not pass:", len(report["failures"]))


if __name__ == "__main__":
    main()
