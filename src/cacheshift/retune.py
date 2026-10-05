"""Fit an exact-cache miss cutoff on tuning data; evaluate once on test data."""

import argparse
from collections import defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import re

import numpy as np

from cacheshift.gateway import DATASET, ROOT
from cacheshift.replay_gateway import ReplayGateway, calibrate_scores, load_dataset, validated_score
from cacheshift.router import LocalBERTRouter, REVISION

SEEDS = (601, 602, 603, 604, 605)


class MemoRouter:
    def __init__(self, router):
        self.router, self.scores = router, {}

    def score(self, text):
        if text not in self.scores:
            self.scores[text] = validated_score(self.router, text)
        return {"router_score": self.scores[text]}


def question_stream(records, split, seed, repeat_fraction=0.5):
    if not math.isfinite(repeat_fraction) or not 0 <= repeat_fraction < 1:
        raise ValueError("repeat_fraction must be between zero (inclusive) and one (exclusive)")
    ids = sorted(qid for qid, row in records.items() if row["split"] == split)
    if not ids:
        raise ValueError("Split has no questions")
    rng = random.Random(seed)
    stream = ids + rng.choices(ids, k=round(len(ids) * repeat_fraction / (1 - repeat_fraction)))
    rng.shuffle(stream)
    return stream


def fit(records, router, stream, target, cache_enabled):
    """Cold, unbounded exact cache; each first occurrence is a miss."""
    seen, scores, misses = set(), [], []
    if not stream:
        raise ValueError("Empty tuning stream")
    for qid in stream:
        row = records.get(qid)
        if row is None or row["split"] != "tuning":
            raise ValueError("Calibration accepts tuning IDs only")
        key = (qid, row["text"])
        if not cache_enabled or key not in seen:
            scores.append(validated_score(router, row["text"]))
            misses.append(qid)
        seen.add(key)
    return {**calibrate_scores(scores, target), "tuning_miss_ids": misses,
            "tuning_scores": scores, "tuning_request_count": len(stream),
            "cache": "exact" if cache_enabled else "none"}


def load_calibration(path, dataset_sha256, router_revision, records=None):
    artifact = json.loads(Path(path).read_text(encoding="utf-8"))
    if (artifact.get("schema") != 1 or artifact.get("cache") != "exact"
            or artifact.get("dataset_sha256") != dataset_sha256
            or artifact.get("router_revision") != router_revision
            or artifact.get("fit_split") != "tuning"):
        raise ValueError("Calibration does not match this dataset, router, or cache")
    scores, ids = artifact.get("tuning_scores"), artifact.get("tuning_miss_ids")
    if not isinstance(scores, list) or not isinstance(ids, list) or len(scores) != len(ids):
        raise ValueError("Invalid tuning evidence")
    if not all(isinstance(qid, str) for qid in ids) or len(set(ids)) != len(ids):
        raise ValueError("Exact-cache calibration must have unique tuning misses")
    if records is not None and any(qid not in records or records[qid]["split"] != "tuning" for qid in ids):
        raise ValueError("Calibration contains a non-tuning question")
    expected = calibrate_scores(scores, artifact["target_strong_share"])
    if artifact.get("threshold") != expected["threshold"]:
        raise ValueError("Calibration threshold does not match its tuning scores")
    return artifact


def is_correct(row, answer):
    # This fixture requests a single ARC choice. Ambiguous/explanatory output is
    # incorrect, not guessed. Gold keys must come from the benchmark export.
    gold = row.get("gold_answer")
    if not isinstance(gold, str) or re.fullmatch(r"[A-E]", gold) is None:
        raise ValueError("Expected an official single-letter gold answer")
    match = re.fullmatch(r"\s*(?:([A-E])[.)]?|\(([A-E])\)|\[([A-E])\])\s*", answer)
    return bool(match and gold in match.groups())


def group_totals(events, records):
    groups = defaultdict(lambda: np.zeros(5))
    for event in events:
        row = records[event["question_id"]]
        groups[row["group_id"]] += [1, not event["cache_hit"], event["route"] == "strong",
                                    is_correct(row, event["answer"]), event["cost_usd"]]
    return groups


def metrics(totals):
    requests, routed, strong, correct, cost = np.moveaxis(totals, -1, 0)
    return np.stack((strong / routed, strong / requests, correct / requests,
                     1000 * cost / requests), axis=-1)


METRICS = ("strong_share_of_routed", "strong_share_of_all", "accuracy", "historical_usd_per_1000")


def paired_report(runs, records, seed, samples=2000):
    """Percentile bootstrap of paired question groups, conditional on fitted cutoffs.

    Resample already-realized traces; do not pretend repeated requests are IID.
    These intervals do not include uncertainty in tuning or the data source.
    """
    grouped = {name: group_totals(events, records) for name, events in runs.items()}
    groups = sorted(grouped["no_cache"])
    if not groups or any(set(values) != set(groups) for values in grouped.values()):
        raise ValueError("Paired runs must contain the same nonempty question groups")
    rng = np.random.default_rng(seed)
    indices = rng.integers(0, len(groups), size=(samples, len(groups)))
    estimates, draws, result = {}, {}, {}
    for name, values in grouped.items():
        array = np.array([values[group] for group in groups])
        estimates[name] = metrics(array.sum(axis=0))
        draws[name] = metrics(array[indices].sum(axis=1))
        result[name] = {metric: {"estimate": float(estimates[name][i]),
                       "ci95": np.quantile(draws[name][:, i], [0.025, 0.975]).tolist()}
                       for i, metric in enumerate(METRICS)}
    result["paired_differences"] = {}
    for name, left, right in (("cache_effect", "cache_untuned", "no_cache"),
                              ("retune_effect", "cache_retuned", "cache_untuned")):
        result["paired_differences"][name] = {
            metric: {"estimate": float(estimates[left][i] - estimates[right][i]),
                     "ci95": np.quantile(draws[left][:, i] - draws[right][:, i], [0.025, 0.975]).tolist()}
            for i, metric in enumerate(METRICS)}
    return result


def acceptance(report, target):
    share = report["cache_retuned"]["strong_share_of_routed"]["estimate"]
    accuracy = report["cache_retuned"]["accuracy"]["estimate"]
    lower, upper = report["no_cache"]["accuracy"]["ci95"]
    return {"share_within_3_percentage_points": abs(share - target) <= 0.03 + 1e-12,
            "accuracy_inside_no_cache_ci": lower <= accuracy <= upper,
            "note": "Inside a baseline CI is the issue's descriptive criterion, not proof of equivalence."}


def run(records, router, run_dir, digest, target=0.5, repeat_fraction=0.5, samples=2000):
    run_dir = Path(run_dir)
    run_dir.mkdir(parents=True, exist_ok=False)
    router = MemoRouter(router)
    report = {"scope": "Development evaluation of originals and exact repeats only",
              "dataset_sha256": digest, "router_revision": REVISION, "target": target,
              "share_denominator": "requests reaching router (cache misses)",
              "repeat_fraction": repeat_fraction, "bootstrap_samples": samples,
              "ci_method": "95% paired question-group percentile bootstrap, conditional on fitted cutoffs",
              "limitations": "Previously exposed development data; no semantic cache, independent confirmatory test, energy, or live latency claims. Tuning uncertainty excluded.",
              "runs": []}
    for seed in SEEDS:
        tuning_stream = question_stream(records, "tuning", seed, repeat_fraction)
        baseline = fit(records, router, tuning_stream, target, False)
        retuned = fit(records, router, tuning_stream, target, True)
        artifact = {**retuned, "schema": 1, "dataset_sha256": digest, "router_revision": REVISION,
                    "fit_split": "tuning", "seed": seed, "repeat_fraction": repeat_fraction}
        (run_dir / f"calibration-{seed}.json").write_text(json.dumps(artifact, indent=2) + "\n", encoding="utf-8")
        # Test is touched only after both cutoffs have been fixed.
        stream = question_stream(records, "test", seed, repeat_fraction)
        events = {}
        for name, calibration, cache in (("no_cache", baseline, False),
                                         ("cache_untuned", baseline, True),
                                         ("cache_retuned", retuned, True)):
            engine = ReplayGateway(records, router, calibration, run_dir / "raw" / f"{seed}-{name}.jsonl",
                                   cache_enabled=cache, dataset_sha256=digest, router_revision=REVISION,
                                   seed=seed, repeats=len(stream) - len(set(stream)))
            events[name] = [engine.answer(qid) for qid in stream]
        estimates = paired_report(events, records, seed, samples)
        trace_hashes = {name: hashlib.sha256((run_dir / "raw" / f"{seed}-{name}.jsonl").read_bytes()).hexdigest()
                        for name in events}
        report["runs"].append({"seed": seed, "baseline_threshold": baseline["threshold"],
                               "retuned_threshold": retuned["threshold"], "metrics": estimates,
                               "trace_sha256": trace_hashes,
                               "acceptance": acceptance(estimates, target)})
        print(f"Completed seed {seed}: {report['runs'][-1]['acceptance']}", flush=True)
    report["all_development_checks_pass"] = all(
        row["acceptance"]["share_within_3_percentage_points"] and row["acceptance"]["accuracy_inside_no_cache_ci"]
        for row in report["runs"])
    (run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--target", type=float, default=0.5)
    parser.add_argument("--repeat-fraction", type=float, default=0.5)
    args = parser.parse_args()
    if not math.isfinite(args.target) or not 0 <= args.target <= 1:
        parser.error("target must be between zero and one")
    if not math.isfinite(args.repeat_fraction) or not 0 <= args.repeat_fraction < 1:
        parser.error("repeat-fraction must be between zero and one (exclusive)")
    records = load_dataset(args.dataset)
    digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    report = run(records, LocalBERTRouter(ROOT / "data/cache/routellm", offline=True),
                 args.run_dir, digest, args.target, args.repeat_fraction)
    print("All development acceptance checks passed:", report["all_development_checks_pass"])


if __name__ == "__main__":
    main()
