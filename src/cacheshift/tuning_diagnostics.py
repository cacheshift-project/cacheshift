"""Check cutoff stability using saved tuning scores only; never fit to test results."""

import argparse
import hashlib
import json
from pathlib import Path
import random

import numpy as np

from cacheshift.replay_gateway import calibrate_scores
from cacheshift.retune import load_calibration, SEEDS


def tuning_points(dataset, calibration):
    """Validate provenance and expose only IDs, groups and saved tuning scores."""
    dataset = Path(dataset)
    artifact = json.loads(Path(calibration).read_text(encoding="utf-8"))
    metadata = {}
    for line in dataset.read_text(encoding="utf-8").splitlines():
        if line.strip():
            row = json.loads(line)
            qid = row["question_id"]
            if qid in metadata:
                raise ValueError("Duplicate question ID")
            metadata[qid] = {"split": row["split"], "group_id": row["group_id"]}
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    artifact = load_calibration(calibration, digest, artifact["router_revision"], metadata)
    tuning_ids = {qid for qid, row in metadata.items() if row["split"] == "tuning"}
    if set(artifact["tuning_miss_ids"]) != tuning_ids:
        raise ValueError("Expected the complete cold exact-cache tuning miss sample")
    group_splits = {}
    for row in metadata.values():
        group = row["group_id"]
        if not isinstance(group, str) or not group:
            raise ValueError("Missing group ID")
        if group in group_splits and group_splits[group] != row["split"]:
            raise ValueError("Question group crosses tuning/test splits")
        group_splits[group] = row["split"]
    points = [{"question_id": qid, "group_id": metadata[qid]["group_id"], "score": score}
              for qid, score in zip(artifact["tuning_miss_ids"], artifact["tuning_scores"])]
    return points, artifact


def diagnose(points, target=0.5, folds=5, samples=2000):
    groups = sorted({point["group_id"] for point in points})
    if not 2 <= folds <= len(groups) or samples < 2:
        raise ValueError("Need at least two groups/folds and bootstrap samples")
    full_fit = calibrate_scores([point["score"] for point in points], target)
    report = {
        "purpose": "Tuning-only diagnostic; no new method selected and no test-set acceptance claim",
        "target": target, "tuning_questions": len(points), "tuning_groups": len(groups),
        "full_tuning_fit": full_fit, "folds": folds, "bootstrap_samples": samples,
        "ci_method": "95% percentile bootstrap of validation question groups, conditional on each fitted cutoff",
        "limitations": "Repeated folds reuse one development tuning sample. They are not independent experiments. Intervals exclude fitting uncertainty and may be degenerate for small or homogeneous folds. No quality, cost, or production claims.",
        "runs": [],
    }
    for seed in SEEDS:
        shuffled = groups.copy()
        random.Random(seed).shuffle(shuffled)
        run = {"seed": seed, "folds": []}
        for index in range(folds):
            validation_groups = set(shuffled[index::folds])
            training = [point for point in points if point["group_id"] not in validation_groups]
            validation = [point for point in points if point["group_id"] in validation_groups]
            fit = calibrate_scores([point["score"] for point in training], target)
            counts = np.array([[sum(point["score"] >= fit["threshold"] for point in validation
                                    if point["group_id"] == group),
                                sum(point["group_id"] == group for point in validation)]
                               for group in sorted(validation_groups)])
            rng = np.random.default_rng(seed * folds + index)
            picks = rng.integers(0, len(counts), size=(samples, len(counts)))
            totals = counts[picks].sum(axis=1)
            ci = np.quantile(totals[:, 0] / totals[:, 1], [0.025, 0.975]).tolist()
            share = float(counts[:, 0].sum() / counts[:, 1].sum())
            run["folds"].append({
                "fold": index, "training_questions": len(training),
                "validation_questions": len(validation), "fit": fit,
                "training_group_ids": sorted(set(groups) - validation_groups),
                "validation_group_ids": sorted(validation_groups),
                "validation_strong_share": share, "validation_ci95": ci,
                "validation_gap_percentage_points": 100 * (share - target),
            })
        report["runs"].append(run)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    points, artifact = tuning_points(args.dataset, args.calibration)
    report = diagnose(points, artifact["target_strong_share"])
    report["dataset_sha256"] = artifact["dataset_sha256"]
    report["router_revision"] = artifact["router_revision"]
    report["calibration_canonical_sha256"] = hashlib.sha256(
        json.dumps(artifact, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    with args.output.open("x", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(report, indent=2) + "\n")
    print(f"Saved tuning-only diagnostics to {args.output}; routing configuration unchanged.")


if __name__ == "__main__":
    main()
