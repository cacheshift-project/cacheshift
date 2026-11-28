"""Re-tuning at scale: the Sprint 3 demo pipeline on every RouterBench MMLU question.

    python -m cacheshift.retune_scale --run-dir experiments/results/retune-scale-<date>

Implements docs/sprints/Sprint_4/Retune_Scale_Protocol.md (fixed before any run): four passes of
the same question stream through ReplayGateway (no cache; cache 0.90; cache 0.90 with the cutoff
re-tuned on half A; cache 0.90 with the cutoff re-tuned on half B), then the one-page report and a
results file with the primary outcome (re-tuned share on held-out half B), the accuracy change, a
cross-fit check and the cache's own effect. Recorded answers only; CPU, roughly 15-25 minutes.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path
import time

from cacheshift import report, retune_log
from cacheshift.cache_quality import request_stream
from cacheshift.gateway import ROOT
from cacheshift.replay_gateway import ReplayGateway, calibrate, load_dataset, summarize
from cacheshift.router import REVISION

DATASET = ROOT / "data/mmlu_all_20261127/questions.jsonl"
DATASET_SHA = "95c9030845ca1a9f64656c0fa41840420d516740c2f6be4e3992f626c9d84cca"
SEED = 601
THRESHOLD = 0.90
TARGET = 0.5


SCORES = ROOT / "data/cache/router_scores.jsonl"


class MemoRouter:
    """The real router, scoring each question text once (single-question scoring, as the gateway does).

    With a path, scores are also kept on disk (one JSON line per text, keyed by its SHA-256 and the
    router revision), so a second experiment or a restarted run reuses them instead of rescoring."""

    def __init__(self, router, path=None):
        self.router, self.scores, self.path = router, {}, Path(path) if path else None
        self.saved = {}
        if self.path and self.path.exists():
            for line in self.path.read_text(encoding="utf-8").splitlines():
                row = json.loads(line)
                if row["revision"] == REVISION:
                    self.saved[row["sha256"]] = row["router_score"]

    def score(self, text):
        if text not in self.scores:
            key = hashlib.sha256(text.encode("utf-8")).hexdigest()
            if key in self.saved:
                self.scores[text] = {"router_score": self.saved[key]}
            else:
                self.scores[text] = self.router.score(text)
                if self.path:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    with self.path.open("a", encoding="utf-8") as out:
                        out.write(json.dumps({"sha256": key, "revision": REVISION,
                                              "router_score": self.scores[text]["router_score"]}) + "\n")
        return self.scores[text]


def through_gateway(name, records, router, calibration, digest, stream, run_dir, seed=SEED, **options):
    engine = ReplayGateway(records, router, calibration, run_dir / f"{name}.jsonl", dataset_sha256=digest,
                           router_revision=REVISION, seed=seed, **options)
    start, events = time.time(), []
    for number, question_id in enumerate(stream, 1):
        events.append(engine.answer(question_id))
        if number % 2000 == 0 or number == len(stream):
            print(f"  {name}: {number:,}/{len(stream):,} requests ({time.time() - start:.0f} s)", flush=True)
    return engine, events


def crossfit(cached, after_a, after_b, records, retune_a, planned):
    """Each question judged with the cutoff fitted on the other half, pooled over all groups."""
    fitted_a = set(retune_a["fit_group_ids"])
    mixed = [b if records[e["question_id"]]["group_id"] in fitted_a else a
             for e, a, b in zip(cached, after_a, after_b)]
    pooled = report.retune_comparison(cached, mixed, records, {"fit_group_ids": [], "threshold": None},
                                      planned)
    pooled.pop("threshold_after")
    return pooled


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--seed", type=int, default=SEED, help="Stream seed (601 in the protocol; others are robustness checks)")
    args = parser.parse_args(argv)
    from cacheshift.router import LocalBERTRouter
    from cacheshift.semantic_cache import EMBEDDING_MODEL, SentenceEmbedder

    digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    if args.dataset == DATASET and digest != DATASET_SHA:
        raise SystemExit("The MMLU set differs from the protocol's; rebuild it with --all-families")
    args.run_dir.mkdir(parents=True, exist_ok=False)
    records = load_dataset(args.dataset)
    test = {qid: row for qid, row in records.items() if row["split"] == "test"}
    router = MemoRouter(LocalBERTRouter(ROOT / "data/cache/routellm", offline=True), SCORES)
    print(f"Setting the cutoff on {len(records) - len(test):,} tuning questions...", flush=True)
    calibration = calibrate(records, router, target=TARGET)
    print(f"Cutoff {calibration['threshold']:.4f} (tuning share {calibration['tuning_strong_share']:.4f})", flush=True)
    embed = SentenceEmbedder(EMBEDDING_MODEL, cache_dir=str(ROOT / "data/cache/embeddings"))
    embed.warm(row["text"] for row in test.values())
    stream = request_stream(test, args.seed)
    print(f"Stream: {len(stream):,} requests ({len(test):,} test questions plus repeats)", flush=True)

    common = dict(records=records, router=router, digest=digest, stream=stream, run_dir=args.run_dir, seed=args.seed)
    cache = dict(semantic_threshold=THRESHOLD, embed=embed)
    runs = {}
    engine, no_cache = through_gateway("no_cache", calibration=calibration, cache_enabled=False, **common)
    runs["no_cache"] = (engine, no_cache)
    cached_name = f"semantic_{THRESHOLD:.2f}"
    engine, cached = through_gateway(cached_name, calibration=calibration, **cache, **common)
    runs[cached_name] = (engine, cached)

    fit_a = retune_log.fit(cached, records, TARGET)
    fit_a.update(previous_threshold=calibration["threshold"], log=f"{cached_name}.jsonl", half="A (even)")
    # Half B: the same rule with the halves swapped (fit on the odd groups).
    odd = [e for e in cached if not retune_log.fit_half(records[e["question_id"]]["group_id"])]
    from cacheshift.replay_gateway import calibrate_scores
    scores = [e["router_score"] for e in odd if not e["cache_hit"]]
    b = calibrate_scores(scores, TARGET)
    fit_b = {"schema": retune_log.SCHEMA, "target_strong_share": TARGET, "threshold": b["threshold"],
             "fit_strong_share": b["tuning_strong_share"], "fit_routed_requests": len(scores),
             "fit_group_ids": sorted({records[e["question_id"]]["group_id"] for e in odd}),
             "held_out_groups": len(fit_a["fit_group_ids"]), "previous_threshold": calibration["threshold"],
             "log": f"{cached_name}.jsonl", "half": "B (odd)",
             "split_rule": "sha256(group_id) odd -> fit half; even -> held out",
             "fit_rule": fit_a["fit_rule"]}
    for name, fitted in (("retune_A", fit_a), ("retune_B", fit_b)):
        (args.run_dir / f"{name}.json").write_text(json.dumps(fitted, indent=2) + "\n", encoding="utf-8")
        print(f"{name}: cutoff {calibration['threshold']:.4f} -> {fitted['threshold']:.4f}", flush=True)
    engine, after_a = through_gateway(f"{cached_name}_retuned_A", calibration={**calibration, "threshold": fit_a["threshold"]},
                                      **cache, **common)
    runs[f"{cached_name}_retuned_A"] = (engine, after_a)
    engine, after_b = through_gateway(f"{cached_name}_retuned_B", calibration={**calibration, "threshold": fit_b["threshold"]},
                                      **cache, **common)
    runs[f"{cached_name}_retuned_B"] = (engine, after_b)

    print("Bootstrapping...", flush=True)
    built = report.build(cached, records, TARGET, fresh_events=no_cache, retuned_events=after_a, retune=fit_a)
    reverse = report.retune_comparison(cached, after_b, records, fit_b, TARGET)
    pooled = crossfit(cached, after_a, after_b, records, fit_a, TARGET)
    x = built["retune"]
    results = {
        "protocol": "docs/sprints/Sprint_4/Retune_Scale_Protocol.md", "dataset_sha256": digest, "seed": args.seed,
        "requests": len(stream), "test_questions": len(test), "question_groups": built["question_groups"],
        "cutoff": calibration["threshold"], "cutoff_retuned_A": fit_a["threshold"], "cutoff_retuned_B": fit_b["threshold"],
        "primary": {"held_out": "half B", "verdict": x["after_band_verdict"],
                    "share_before": x["before"]["strong_share_of_routed"], "share_after": x["after"]["strong_share_of_routed"],
                    "drift_after": x["after_drift_from_plan"], "held_out_groups": x["held_out_groups"],
                    "held_out_requests": x["held_out_requests"]},
        "accuracy_change": x["change"]["accuracy"], "accuracy_range_above_margin": x["accuracy_range_above_margin"],
        "cost_change_per_1000": x["change"]["usd_per_1000"],
        "reverse_half": {"verdict": reverse["after_band_verdict"], "share_after": reverse["after"]["strong_share_of_routed"],
                         "drift_after": reverse["after_drift_from_plan"], "accuracy_change": reverse["change"]["accuracy"]},
        "crossfit": {"verdict": pooled["after_band_verdict"], "share_before": pooled["before"]["strong_share_of_routed"],
                     "share_after": pooled["after"]["strong_share_of_routed"], "drift_after": pooled["after_drift_from_plan"],
                     "accuracy_change": pooled["change"]["accuracy"], "cost_change_per_1000": pooled["change"]["usd_per_1000"],
                     "groups": pooled["held_out_groups"]},
        "original_cutoff": {"drift": built["rates"]["drift_from_plan"], "verdict": built["band_verdict"],
                            "cache_effect_on_share": built["paired"]["strong_share_change"],
                            "accuracy_change_vs_fresh": built["paired"]["accuracy_change"]},
        "runs": {name: {"config_id": engine.config_id, "config": engine.config, "summary": summarize(events, TARGET)}
                 for name, (engine, events) in runs.items()},
    }
    (args.run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    (args.run_dir / "runs.json").write_text(json.dumps({"calibration": {key: calibration[key] for key in
                                            ("target_strong_share", "threshold", "tuning_strong_share")},
                                            "runs": results["runs"]}, indent=2) + "\n", encoding="utf-8")
    report.main(["--log", str(args.run_dir / f"{cached_name}.jsonl"), "--fresh-log", str(args.run_dir / "no_cache.jsonl"),
                 "--dataset", str(args.dataset), "--config", str(args.run_dir / "runs.json"),
                 "--retuned-log", str(args.run_dir / f"{cached_name}_retuned_A.jsonl"),
                 "--retune", str(args.run_dir / "retune_A.json"), "--out", str(args.run_dir / "report.html"),
                 "--title", "Re-tuning at scale: every RouterBench MMLU question"])
    for name in runs:   # logs are large; keep them compressed
        path = args.run_dir / f"{name}.jsonl"
        with path.open("rb") as source, gzip.open(path.with_suffix(".jsonl.gz"), "wb", compresslevel=9) as target:
            target.write(source.read())
        path.unlink()
    p, c = results["primary"], results["crossfit"]
    print(f"\nPrimary (held-out half B): {report.pct(p['share_after']['estimate'])} "
          f"({report.rng(p['share_after'], report.pct)}) -> {p['verdict']}")
    print(f"Cross-fit (all groups): {report.pct(c['share_after']['estimate'])} ({report.rng(c['share_after'], report.pct)}) -> {c['verdict']}")


if __name__ == "__main__":
    main()
