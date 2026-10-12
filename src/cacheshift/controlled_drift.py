"""Explicit score-skew stress test; single-prompt scoring and tuning-only fits."""

import argparse
import hashlib
import json
from pathlib import Path
import random

import numpy as np

from cacheshift.gateway import ROOT
from cacheshift.replay_gateway import ReplayGateway, load_dataset, validated_score
from cacheshift.retune import SEEDS, acceptance, fit, group_totals, metrics, paired_report
from cacheshift.router import LocalBERTRouter, REVISION

POLICIES = ("uniform", "high", "low")


def write(path, value):
    Path(path).write_bytes((json.dumps(value, indent=2) + "\n").encode())


class FixedRouter:
    def __init__(self, records, scores):
        self.scores = {records[qid]["text"]: score for qid, score in scores.items()}

    def score(self, text):
        return {"router_score": self.scores[text]}


def stream(records, scores, split, seed, policy, popularity_cutoff):
    if policy not in POLICIES:
        raise ValueError("Unknown repeat policy")
    ids = sorted(qid for qid, row in records.items() if row["split"] == split)
    if not ids:
        raise ValueError("Empty split")
    weights = []
    for qid in ids:
        high = scores[qid] >= popularity_cutoff
        weights.append(1 if policy == "uniform" else 2 if high == (policy == "high") else 1)
    rng = random.Random(seed)
    result = ids + rng.choices(ids, weights=weights, k=len(ids))
    rng.shuffle(result)
    return result


def score_split(records, router, split, path, digest):
    scores = {}
    ids = sorted(qid for qid, row in records.items() if row["split"] == split)
    for i, qid in enumerate(ids, 1):
        scores[qid] = validated_score(router, records[qid]["text"])
        if i % 32 == 0 or i == len(ids):
            print(f"Single scoring {split}: {i}/{len(ids)}", flush=True)
    artifact = {"dataset_sha256": digest, "router_revision": REVISION,
                "scoring_mode": "single", "split": split, "scores": scores}
    write(path, artifact)
    return scores


def error_reduction(events, records, seed, target=0.5, samples=2000):
    grouped = {name: group_totals(trace, records) for name, trace in events.items()}
    groups = sorted(grouped["no_cache"])
    indices = np.random.default_rng(seed).integers(0, len(groups), size=(samples, len(groups)))
    estimates, draws = {}, {}
    for name in ("cache_untuned", "cache_retuned"):
        array = np.array([grouped[name][group] for group in groups])
        estimates[name] = float(metrics(array.sum(axis=0))[0])
        draws[name] = metrics(array[indices].sum(axis=1))[:, 0]
    reduction = abs(estimates["cache_untuned"] - target) - abs(estimates["cache_retuned"] - target)
    ci = np.quantile(abs(draws["cache_untuned"] - target) - abs(draws["cache_retuned"] - target), [.025, .975])
    return {"estimate": reduction, "ci95": ci.tolist()}


def checks(report, reduction):
    result = acceptance(report, .5)
    effect = report["paired_differences"]["cache_effect"]["strong_share_of_routed"]
    low, high = effect["ci95"]
    result.update({"material_cache_drift": abs(effect["estimate"]) >= .05 and (low > 0 or high < 0),
                   "material_error_reduction": reduction["estimate"] >= .03 and reduction["ci95"][0] > 0})
    result["mechanism_checks_pass"] = all(result[key] for key in (
        "share_within_3_percentage_points", "accuracy_inside_no_cache_ci",
        "material_cache_drift", "material_error_reduction"))
    return result


def audit_old(records, scores, old_dir, digest):
    old_dir = Path(old_dir)
    original = json.loads((old_dir / "report.json").read_text())
    if original["dataset_sha256"] != digest:
        raise ValueError("Old report dataset differs")
    calibration = json.loads((old_dir / "calibration-601.json").read_text())
    old = dict(zip(calibration["tuning_miss_ids"], calibration["tuning_scores"]))
    trace = old_dir / "raw/601-cache_retuned.jsonl"
    if hashlib.sha256(trace.read_bytes()).hexdigest() != original["runs"][0]["trace_sha256"]["cache_retuned"]:
        raise ValueError("Old raw trace checksum differs")
    for line in trace.read_text().splitlines():
        event = json.loads(line)
        if not event["cache_hit"]:
            old[event["question_id"]] = event["router_score"]
    if set(old) != set(scores) or set(old) != set(records):
        raise ValueError("Incomplete score comparison")
    cutoff = calibration["threshold"]
    near = sorted(old, key=lambda qid: abs(old[qid] - cutoff))[:8]
    flips = {}
    for run in original["runs"]:
        for kind in ("baseline_threshold", "retuned_threshold"):
            threshold = run[kind]
            flips[f"{run['seed']}-{kind}"] = {
                split: [qid for qid in old if records[qid]["split"] == split and
                        (old[qid] >= threshold) != (scores[qid] >= threshold)]
                for split in ("tuning", "test")}
    return {"old_report_sha256": hashlib.sha256((old_dir / "report.json").read_bytes()).hexdigest(),
            "questions": len(old), "max_absolute_score_difference": max(abs(old[qid] - scores[qid]) for qid in old),
            "decision_flips_at_old_cutoffs": flips,
            "boundary_questions": [{"question_id": qid, "batch_score": old[qid],
                                    "single_score": scores[qid], "old_cutoff": cutoff} for qid in near]}


def run(records, router, output, digest, old_dir=None, samples=2000):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    tuning = score_split(records, router, "tuning", output / "scores-tuning.json", digest)
    tuning_router = FixedRouter(records, tuning)
    tuning_ids = sorted(tuning)
    retuned = fit(records, tuning_router, tuning_ids, .5, True, threshold_rule="midgap")
    cutoff = retuned["threshold"]
    artifact = {**retuned, "schema": 1, "dataset_sha256": digest, "router_revision": REVISION,
                "fit_split": "tuning", "scoring_mode": "single", "seed": 601, "repeat_fraction": .5}
    write(output / "calibration.json", artifact)
    fits = {}
    for policy in POLICIES:
        for seed in SEEDS:
            tuning_stream = stream(records, tuning, "tuning", seed, policy, cutoff)
            baseline = fit(records, tuning_router, tuning_stream, .5, False, threshold_rule="midgap")
            fits[(policy, seed)] = baseline
    # Every cutoff is frozen before any new test score or routed accuracy is evaluated.
    write(output / "frozen-fits.json", {"popularity_cutoff": cutoff, "target": .5,
          "baseline_fits": [{"policy": policy, "seed": seed, **fit_} for (policy, seed), fit_ in fits.items()]})
    test = score_split(records, router, "test", output / "scores-test.json", digest)
    scores = {**tuning, **test}
    memo = FixedRouter(records, scores)
    if old_dir is not None:
        write(output / "batch-single-audit.json", audit_old(records, scores, old_dir, digest))
    report = {"scope": "Synthetic score-skew mechanism test on exposed development data",
              "dataset_sha256": digest, "router_revision": REVISION, "scoring_mode": "single",
              "target": .5, "repeat_fraction": .5, "popularity_weight_ratio": "2:1",
              "popularity_cutoff": cutoff, "threshold_rule": "midgap", "bootstrap_samples": samples,
              "limitations": "Score-conditioned engineered popularity, not real traffic; exposed pool and repeated seeds; conditional paired group intervals exclude fitting uncertainty; historical costs; no semantic cache or live model calls.",
              "runs": []}
    for policy in POLICIES:
        for seed in SEEDS:
            test_stream = stream(records, scores, "test", seed, policy, cutoff)
            events, hashes = {}, {}
            for name, calibration, cache in (("no_cache", fits[(policy, seed)], False),
                                             ("cache_untuned", fits[(policy, seed)], True),
                                             ("cache_retuned", retuned, True)):
                path = output / "raw" / f"{policy}-{seed}-{name}.jsonl"
                engine = ReplayGateway(records, memo, calibration, path, cache_enabled=cache,
                                       dataset_sha256=digest, router_revision=REVISION, seed=seed,
                                       repeats=len(test_stream) - len(set(test_stream)))
                events[name] = [engine.answer(qid) for qid in test_stream]
                hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
            stats = paired_report(events, records, seed, samples)
            reduction = error_reduction(events, records, seed, samples=samples)
            result = checks(stats, reduction)
            report["runs"].append({"policy": policy, "seed": seed,
                    "baseline_threshold": fits[(policy, seed)]["threshold"], "retuned_threshold": cutoff,
                    "metrics": stats, "absolute_target_error_reduction": reduction,
                    "checks": result, "trace_sha256": hashes})
            print(f"{policy} seed {seed}: {result}", flush=True)
    report["all_skew_mechanism_checks_pass"] = all(row["checks"]["mechanism_checks_pass"]
                         for row in report["runs"] if row["policy"] != "uniform")
    write(output / "report.json", report)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=ROOT / "data/mmlu_retune_20261007/questions.jsonl")
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--audit-old", type=Path)
    args = parser.parse_args()
    records = load_dataset(args.dataset)
    digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    report = run(records, LocalBERTRouter(ROOT / "data/cache/routellm", offline=True),
                 args.run_dir, digest, args.audit_old)
    print("All skew mechanism checks pass:", report["all_skew_mechanism_checks_pass"])


if __name__ == "__main__":
    main()
