"""Issue #49: re-tune the router's cutoff on the questions a gateway run actually sent to it.

    python -m cacheshift.retune_log --log run/semantic_0.90.jsonl --config run/runs.json --out run/retune.json

Story 3 (#5, option A): re-tuning should bring the expensive-model share back to plan, and the
report shows what that costs in accuracy so the user can decide whether to apply it.

The run's question groups are split into two fixed halves by a hash of the group ID. The new
cutoff is fitted on the router scores of the first half's requests that got past the cache (the
traffic the router really saw), with the same rule the gateway uses to set its cutoff. The second
half is held out: the report (--retuned-log with --retune) compares the old and new cutoffs only
on those groups, so the new cutoff is never judged on the questions it was fitted to. Labels and
answers are never read here.
"""

import argparse
import hashlib
import json
import math
from pathlib import Path
import sys

from cacheshift.replay_gateway import calibrate_scores
from cacheshift.report import planned_share_from, read_log

SCHEMA = 1


def fit_half(group_id):
    """True for the half of question groups the cutoff is fitted on."""
    return int(hashlib.sha256(group_id.encode("utf-8")).hexdigest(), 16) % 2 == 0


def previous_threshold_from(config_path):
    config = json.loads(Path(config_path).read_text(encoding="utf-8"))
    candidates = [config.get("calibration"), config.get("config")]
    runs = config.get("runs")
    if isinstance(runs, dict):
        candidates += [run.get("config") for run in runs.values()]
    for candidate in candidates:
        if isinstance(candidate, dict) and isinstance(candidate.get("threshold"), (int, float)):
            return float(candidate["threshold"])
    return None


def fit(events, records, planned_share):
    """New cutoff from the fit half's routed requests; returns the retune record."""
    if not math.isfinite(planned_share) or not 0 <= planned_share <= 1:
        raise ValueError("The planned share must be between 0 and 1")
    scores, fit_groups, held_out = [], set(), set()
    for event in events:
        row = records.get(event["question_id"])
        if row is None:
            raise ValueError(f"Question {event['question_id']} is not in the dataset; use the run's --dataset")
        group = row["group_id"]
        if not fit_half(group):
            held_out.add(group)
            continue
        fit_groups.add(group)
        if event["cache_hit"]:
            continue
        score = event.get("router_score")
        if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score) or not 0 <= score <= 1:
            raise ValueError(f"Routed request for {event['question_id']} has no valid router_score")
        scores.append(float(score))
    if not scores or not held_out:
        raise ValueError("The run is too small to split into a fit half and a held-out half")
    calibration = calibrate_scores(scores, planned_share)
    return {"schema": SCHEMA, "target_strong_share": planned_share, "threshold": calibration["threshold"],
            "fit_strong_share": calibration["tuning_strong_share"], "fit_routed_requests": len(scores),
            "fit_group_ids": sorted(fit_groups), "held_out_groups": len(held_out),
            "split_rule": "sha256(group_id) even -> fit half; odd -> held out",
            "fit_rule": "replay_gateway.calibrate_scores on the fit half's router scores"}


def load(path):
    retune = json.loads(Path(path).read_text(encoding="utf-8"))
    if retune.get("schema") != SCHEMA or not isinstance(retune.get("fit_group_ids"), list):
        raise ValueError(f"{path} is not a re-tune file from cacheshift.retune_log")
    return retune


def main(argv=None):
    from cacheshift.gateway import DATASET
    from cacheshift.replay_gateway import load_dataset

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--log", type=Path, required=True, help="Gateway request log (JSONL) with the cache on")
    parser.add_argument("--dataset", type=Path, default=DATASET, help="Replay dataset the run used")
    plan = parser.add_mutually_exclusive_group(required=True)
    plan.add_argument("--planned-share", type=float, help="Planned expensive-model share, e.g. 0.5")
    plan.add_argument("--config", type=Path, help="The run's runs.json/report.json (target share and current cutoff)")
    parser.add_argument("--out", type=Path, required=True, help="Re-tune file to write (JSON)")
    args = parser.parse_args(argv)
    try:
        records = load_dataset(args.dataset)
        planned = args.planned_share if args.planned_share is not None else planned_share_from(args.config)
        retune = fit(read_log(args.log), records, planned)
    except (OSError, ValueError, KeyError) as exc:
        parser.exit(1, f"Could not re-tune: {exc}\n")
    retune["previous_threshold"] = previous_threshold_from(args.config) if args.config else None
    retune["log"] = args.log.name
    retune["log_sha256"] = hashlib.sha256(args.log.read_bytes()).hexdigest()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(retune, indent=2) + "\n", encoding="utf-8", newline="\n")
    before = "" if retune["previous_threshold"] is None else f" (was {retune['previous_threshold']:.4f})"
    print(f"New cutoff {retune['threshold']:.4f}{before}, fitted on {retune['fit_routed_requests']} routed requests "
          f"from {len(retune['fit_group_ids'])} question groups; {retune['held_out_groups']} groups held out.")
    print(f"Wrote {args.out}. Run the gateway with this cutoff on the same stream, then pass "
          f"--retuned-log and --retune {args.out.name} to cacheshift.report.")


if __name__ == "__main__":
    sys.exit(main())
