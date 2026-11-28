"""Difference check: does trimming shared text before reusing an answer fix the template problem?

    python -m cacheshift.difference_check --run-dir experiments/results/difference-check-<date> \
        --mmlu-fresh experiments/results/retune-scale-20261127/no_cache.jsonl.gz

Implements docs/sprints/Sprint_4/Difference_Check_Protocol.md (fixed before any run): the MMLU stream
of the re-tuning-at-scale run through the cache with the difference check at several settings
(paired against that run's no-cache log), the ARC Sprint 3 demo stream at 0.90 and 0.80 with the
check, and the 120 rewordings. Recorded answers only.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from cacheshift import report
from cacheshift.cache_quality import request_stream
from cacheshift.gateway import ROOT
from cacheshift.replay_gateway import calibrate, load_dataset
from cacheshift.retune_scale import DATASET, DATASET_SHA, SCORES, MemoRouter, through_gateway
from cacheshift.reworded_check import REWORDINGS, reworded_prompt
from cacheshift.semantic_cache import SemanticCache

ARC = ROOT / "data/retune_holdout_20261007/questions.jsonl"
SEED = 601
TARGET = 0.5
MMLU_RUNS = [(0.90, 0.80), (0.90, 0.70), (0.90, 0.90), (0.80, 0.80)]   # (match setting, check); primary first
ARC_RUNS = [(0.90, 0.80), (0.80, 0.80)]


def read_events(path):
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def summarize_run(cached, fresh, records):
    built = report.build(cached, records, TARGET, fresh_events=fresh)
    r, t = built["rates"], built["totals"]
    return {"wrong_caused": t["wrong_question_wrong"], "wrong_caused_rate": r["wrong_question_wrong_rate"],
            "wrong_question_hits": t["wrong_question"], "hit_rate": r["hit_rate"], "usd_per_1000": r["usd_per_1000"],
            "accuracy": r["accuracy"], "accuracy_change_vs_fresh": built["paired"]["accuracy_change"],
            "share": r["strong_share_of_routed"], "drift": r["drift_from_plan"], "band_verdict": built["band_verdict"],
            "cache_effect_on_share": built["paired"]["strong_share_change"]}


def stream_runs(name, dataset, runs, fresh_log, router, embed, run_dir):
    records = load_dataset(dataset)
    digest = hashlib.sha256(Path(dataset).read_bytes()).hexdigest()
    calibration = calibrate(records, router, target=TARGET)
    test = {qid: row for qid, row in records.items() if row["split"] == "test"}
    embed.warm(row["text"] for row in test.values())
    stream = request_stream(test, SEED)
    common = dict(records=records, router=router, calibration=calibration, digest=digest, stream=stream, run_dir=run_dir)
    if fresh_log:
        fresh = read_events(fresh_log)
        if [e["question_id"] for e in fresh] != stream:
            raise SystemExit(f"{fresh_log} is not this stream")
    else:
        _, fresh = through_gateway(f"{name}_no_cache", cache_enabled=False, **common)
    out = {"cutoff": calibration["threshold"], "requests": len(stream), "runs": {}}
    for setting, check in [(s, None) for s in sorted({s for s, _ in runs}, reverse=True) if not fresh_log] + runs:
        label = f"{setting:.2f}" + ("" if check is None else f"+check{check:.2f}")
        engine, cached = through_gateway(f"{name}_{label}", semantic_threshold=setting, embed=embed,
                                         semantic_verify=check, **common)
        out["runs"][label] = {**summarize_run(cached, fresh, records), "rejected_by_check": engine.semantic.rejected,
                              "config_id": engine.config_id}
        s = out["runs"][label]
        print(f"{name} {label}: wrong caused {s['wrong_caused']} ({report.pct(s['wrong_caused_rate']['estimate'], 2)}, "
              f"{report.rng(s['wrong_caused_rate'], lambda v: report.pct(v, 2))}); hits {report.pct(s['hit_rate']['estimate'])}; "
              f"accuracy vs fresh {report.pts(s['accuracy_change_vs_fresh']['estimate'])} "
              f"({report.rng(s['accuracy_change_vs_fresh'], report.pts)}); rejected {s['rejected_by_check']}", flush=True)
    return out


def rewordings_check(embed):
    records = load_dataset(DATASET)
    rewordings = [json.loads(line) for line in REWORDINGS.read_text(encoding="utf-8").splitlines() if line.strip()]
    test = sorted((row for row in records.values() if row["split"] == "test"), key=lambda r: r["question_id"])
    embed.warm(row["text"] for row in test)
    out = {}
    for setting, check in [(0.90, None), (0.90, 0.80), (0.80, None), (0.80, 0.80)]:
        cache = SemanticCache(embed, setting, verify=check)
        for row in test:
            cache.insert(row["text"], {"question_id": row["question_id"]})
        caught = other = 0
        for item in rewordings:
            text = reworded_prompt(records[item["question_id"]]["text"], item["original"], item["reworded"])
            entry, _ = cache.lookup(text)
            if entry is not None:
                caught += entry["question_id"] == item["question_id"]
                other += entry["question_id"] != item["question_id"]
        label = f"{setting:.2f}" + ("" if check is None else f"+check{check:.2f}")
        out[label] = {"caught_own_original": caught, "matched_other_question": other, "n": len(rewordings)}
        print(f"rewordings {label}: caught {caught}/{len(rewordings)}, other question {other}", flush=True)
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--mmlu-fresh", type=Path, required=True, help="The re-tuning-at-scale run's no_cache log")
    args = parser.parse_args(argv)
    from cacheshift.router import LocalBERTRouter
    from cacheshift.semantic_cache import EMBEDDING_MODEL, SentenceEmbedder

    if hashlib.sha256(DATASET.read_bytes()).hexdigest() != DATASET_SHA:
        raise SystemExit("The MMLU set differs from the protocol's; rebuild it with --all-families")
    args.run_dir.mkdir(parents=True, exist_ok=False)
    router = MemoRouter(LocalBERTRouter(ROOT / "data/cache/routellm", offline=True), SCORES)
    embed = SentenceEmbedder(EMBEDDING_MODEL, cache_dir=str(ROOT / "data/cache/embeddings"))
    results = {"protocol": "docs/sprints/Sprint_4/Difference_Check_Protocol.md",
               "baseline_mmlu_0.90": "experiments/results/retune-scale-20261127 (567 wrong caused, 4.12% [3.64, 4.66])"}
    results["arc"] = stream_runs("arc", ARC, ARC_RUNS, None, router, embed, args.run_dir)
    results["rewordings"] = rewordings_check(embed)
    results["mmlu"] = stream_runs("mmlu", DATASET, MMLU_RUNS, args.mmlu_fresh, router, embed, args.run_dir)
    (args.run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    for path in args.run_dir.glob("*.jsonl"):
        with path.open("rb") as source, gzip.open(path.with_suffix(".jsonl.gz"), "wb", compresslevel=9) as target:
            target.write(source.read())
        path.unlink()


if __name__ == "__main__":
    main()
