"""#47 cross-check: does the semantic cache behave the same inside the gateway as in Story 2?

Replays one question stream (Story 2's rule: every test question once plus uniform repeats,
seed 601) through the replay gateway with the semantic cache at each setting, and through
Story 2's own offline replay with the same stream and embedder. The gateway passes when every
request gets the same hit/miss decision and, on a hit, the same matched question. Its rate of
saved answers served to a different question is shown next to Story 2's published range.

The gateway only serves the holdout's test split (485 of the 970 questions Story 2 used), so
the rates are expected to be close to Story 2's, not identical; the request-by-request match
is the pass/fail check. The gateway logs are written to the run directory and can be turned
into the one-page report (#48).

Run: python -m cacheshift.semantic_gateway_check --run-dir experiments/results/semantic-gateway-check-<date>
"""

import argparse
import hashlib
import json
from pathlib import Path

from cacheshift.cache_quality import replay, request_stream, setting_name
from cacheshift.gateway import ROOT, prepare
from cacheshift.replay_gateway import STRONG, ReplayGateway
from cacheshift.router import REVISION
from cacheshift.semantic_cache import EMBEDDING_MODEL, SemanticCache

DATASET = ROOT / "data/retune_holdout_20261007/questions.jsonl"
STORY2 = ROOT / "experiments/results/cache-quality-20261012/report.json"
THRESHOLDS = (0.90, 0.80)
SEED = 601


def story2_range(story2, threshold, seed=SEED, model=STRONG):
    for run in story2["runs"]:
        if run["seed"] == seed and run["model"] == model and run["setting"] == setting_name(threshold):
            return run["false_hit_rate"]
    raise ValueError(f"Story 2 report has no run for seed {seed}, {model}, {setting_name(threshold)}")


def compare(gateway_events, offline_events):
    """Request-by-request agreement on hit/miss and, for hits, on the matched question."""
    mismatches = []
    for number, (g, o) in enumerate(zip(gateway_events, offline_events)):
        same = g["cache_hit"] == o["cache_hit"] and (not g["cache_hit"]
                                                     or g["matched_question_id"] == o["matched_question_id"])
        if not same:
            mismatches.append({"request": number, "question_id": g["question_id"],
                               "gateway": [g["cache_hit"], g["matched_question_id"]],
                               "story2": [o["cache_hit"], o["matched_question_id"] if o["cache_hit"] else None]})
    return mismatches


def check(records, stream, router, calibration, embed, run_dir, digest, thresholds=THRESHOLDS, story2=None):
    test = {qid: row for qid, row in records.items() if row["split"] == "test"}
    result = {"purpose": "#47: semantic cache inside the gateway vs Story 2's offline replay",
              "dataset_sha256": digest, "embedding_model": getattr(embed, "model_name", "custom"),
              "router_revision": REVISION, "seed": SEED, "requests": len(stream),
              "unique_questions": len(set(stream)), "settings": {}}
    for threshold in thresholds:
        gateway = ReplayGateway(records, router, calibration, Path(run_dir) / f"semantic_{threshold:.2f}.jsonl",
                                dataset_sha256=digest, router_revision=REVISION,
                                semantic_threshold=threshold, embed=embed)
        gateway_events = [gateway.answer(qid) for qid in stream]
        offline_events = replay(test, stream, SemanticCache(embed, threshold), STRONG)
        mismatches = compare(gateway_events, offline_events)
        hits = sum(e["cache_hit"] for e in gateway_events)
        wrong = sum(e["cache_hit"] and e["matched_question_id"] != e["question_id"] for e in gateway_events)
        entry = {"config_id": gateway.config_id, "log": gateway.log_path.name,
                 "hits": hits, "wrong_question_hits": wrong,
                 "hit_rate": hits / len(stream), "wrong_question_rate": wrong / len(stream),
                 "story2_offline_wrong_question_hits": sum(e["label"].startswith("false_hit") for e in offline_events),
                 "mismatches": len(mismatches), "first_mismatches": mismatches[:10],
                 "passes": not mismatches}
        if story2 is not None:
            entry["story2_published_wrong_question_rate"] = story2_range(story2, threshold)
        result["settings"][setting_name(threshold)] = entry
        print(f"{setting_name(threshold)}: {hits} hits, {wrong} to a different question, "
              f"{len(mismatches)} mismatches with Story 2", flush=True)
    result["passes"] = all(entry["passes"] for entry in result["settings"].values())
    return result


def markdown(result):
    lines = ["# Semantic cache in the gateway vs Story 2 (#47)", "",
             f"{result['requests']:,} requests ({result['unique_questions']} test questions plus uniform repeats, "
             f"seed {result['seed']}). Pass = every request gets the same hit/miss decision and matched question "
             "in the gateway as in Story 2's offline replay.", "",
             "| Setting | Hits | Answer served to a different question | Story 2 published (970 questions) | Mismatches | Pass |",
             "|---|---:|---:|---:|---:|---|"]
    for name, e in result["settings"].items():
        published = e.get("story2_published_wrong_question_rate")
        if published and published["ci95"]:
            lo, hi = published["ci95"]
            published = f"{100 * published['estimate']:.1f}% [{100 * lo:.1f}, {100 * hi:.1f}]"
        else:
            published = "–"
        lines.append(f"| {name} | {e['hits']} ({100 * e['hit_rate']:.1f}%) | {e['wrong_question_hits']} "
                     f"({100 * e['wrong_question_rate']:.1f}%) | {published} | {e['mismatches']} | "
                     f"{'yes' if e['passes'] else '**no**'} |")
    lines += ["", "The gateway serves only the holdout's test split, so its rates are expected to be close to "
              "Story 2's, not identical. The request-by-request match is the pass/fail check.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--story2", type=Path, default=STORY2)
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/cache/embeddings")
    args = parser.parse_args()
    from cacheshift.semantic_cache import SentenceEmbedder

    args.run_dir.mkdir(parents=True, exist_ok=False)
    records, router, calibration, digest = prepare(args.dataset)
    test = {qid: row for qid, row in records.items() if row["split"] == "test"}
    embed = SentenceEmbedder(EMBEDDING_MODEL, cache_dir=str(args.cache_dir))
    embed.warm(row["text"] for row in test.values())
    stream = request_stream(test, SEED)
    story2 = json.loads(args.story2.read_text(encoding="utf-8")) if args.story2.exists() else None
    result = check(records, stream, router, calibration, embed, args.run_dir, digest, story2=story2)
    result["calibration"] = {key: calibration[key] for key in ("target_strong_share", "threshold", "tuning_strong_share")}
    result["story2_report_sha256"] = hashlib.sha256(args.story2.read_bytes()).hexdigest() if story2 else None
    (args.run_dir / "report.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    (args.run_dir / "report.md").write_text(markdown(result), encoding="utf-8")
    print(markdown(result))
    return 0 if result["passes"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
