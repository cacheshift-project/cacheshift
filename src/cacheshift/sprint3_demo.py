"""Sprint 3 demo (#50): a question stream through the live gateway, then the one-page report.

Starts the replay gateway's HTTP server on this machine, once with no cache and once with the
semantic cache (#47), and sends the same question stream to each: every ARC holdout test question
once plus uniform repeats (Story 2's rule, seed 601). Then (#49, skip with --no-retune) it re-tunes
the cutoff on the cached run's routed requests from half of the question groups and sends the
stream a third time with the new cutoff. Finally it writes the one-page report (#48), comparing the
cached run against the no-cache run of the same stream, so the cache's own effect on cost, accuracy
and expensive-model share is separated from the router's cutoff, plus the re-tuning trade-off on
the held-out half.

    python -m cacheshift.sprint3_demo --run-dir experiments/results/sprint3-demo-<date> [--threshold 0.90] [--no-retune]

Runs on a laptop CPU in a few minutes per pass; no API calls (recorded answers).
"""

import argparse
import json
from pathlib import Path
from urllib.request import Request, urlopen

from cacheshift.cache_quality import request_stream
from cacheshift.demo import serve
from cacheshift.gateway import ROOT, create_app, prepare
from cacheshift.replay_gateway import ReplayGateway, summarize
from cacheshift.router import REVISION
from cacheshift.semantic_cache import EMBEDDING_MODEL

DATASET = ROOT / "data/retune_holdout_20261007/questions.jsonl"
SEED = 601


def send(url, stream, name):
    events = []
    for number, question_id in enumerate(stream, 1):
        request = Request(url + "/replay", data=json.dumps({"question_id": question_id}).encode(),
                          headers={"Content-Type": "application/json"}, method="POST")
        with urlopen(request, timeout=120) as response:
            events.append(json.load(response))
        if number % 200 == 0 or number == len(stream):
            print(f"  {name}: {number}/{len(stream)} requests", flush=True)
    return events


def run(records, router, calibration, digest, embed, stream, run_dir, threshold, retune=True):
    report = {"purpose": "Sprint 3 demo (#50): same question stream through the live gateway with and without the cache",
              "dataset_sha256": digest, "seed": SEED, "router_revision": REVISION,
              "calibration": {key: calibration[key] for key in ("target_strong_share", "threshold", "tuning_strong_share")},
              "requests": len(stream), "unique_questions": len(set(stream)), "runs": {}}
    cached = f"semantic_{threshold:.2f}"

    def through_gateway(name, cutoff, **options):
        engine = ReplayGateway(records, router, cutoff, run_dir / f"{name}.jsonl", dataset_sha256=digest,
                               router_revision=REVISION, **options)
        with serve(create_app(engine)) as url:
            events = send(url, stream, name)
        report["runs"][name] = {"config": engine.config, "config_id": engine.config_id,
                                "summary": summarize(events, calibration["target_strong_share"])}

    through_gateway("no_cache", calibration, cache_enabled=False)
    through_gateway(cached, calibration, semantic_threshold=threshold, embed=embed)
    if retune:
        # #49: re-tune the cutoff on the traffic the router saw in half of the question groups,
        # then run the same stream again with the new cutoff; the report compares the two on
        # the held-out half.
        from cacheshift import retune_log
        from cacheshift.report import read_log

        fitted = retune_log.fit(read_log(run_dir / f"{cached}.jsonl"), records, calibration["target_strong_share"])
        fitted.update(previous_threshold=calibration["threshold"], log=f"{cached}.jsonl")
        (run_dir / "retune.json").write_text(json.dumps(fitted, indent=2) + "\n", encoding="utf-8")
        print(f"Re-tuned cutoff {calibration['threshold']:.4f} -> {fitted['threshold']:.4f}", flush=True)
        through_gateway(f"{cached}_retuned", {**calibration, "threshold": fitted["threshold"]},
                        semantic_threshold=threshold, embed=embed)
    (run_dir / "runs.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--threshold", type=float, default=0.90, help="Semantic cache setting (cosine similarity)")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/cache/embeddings")
    parser.add_argument("--no-retune", action="store_true", help="Skip the re-tuning step (#49)")
    args = parser.parse_args()
    from cacheshift.semantic_cache import SentenceEmbedder

    args.run_dir.mkdir(parents=True, exist_ok=False)
    records, router, calibration, digest = prepare(args.dataset)
    test = {qid: row for qid, row in records.items() if row["split"] == "test"}
    embed = SentenceEmbedder(EMBEDDING_MODEL, cache_dir=str(args.cache_dir))
    embed.warm(row["text"] for row in test.values())
    stream = request_stream(test, SEED)
    times = "twice" if args.no_retune else "three times (no cache, cache, cache with the re-tuned cutoff)"
    print(f"Sending {len(stream)} requests ({len(test)} questions plus repeats) to the gateway, {times}", flush=True)
    run(records, router, calibration, digest, embed, stream, args.run_dir, args.threshold, retune=not args.no_retune)

    cached = args.run_dir / f"semantic_{args.threshold:.2f}.jsonl"
    report_args = ["--log", str(cached), "--fresh-log", str(args.run_dir / "no_cache.jsonl"),
                   "--dataset", str(args.dataset), "--config", str(args.run_dir / "runs.json"),
                   "--out", str(args.run_dir / "report.html")]
    if not args.no_retune:
        report_args += ["--retuned-log", str(args.run_dir / f"semantic_{args.threshold:.2f}_retuned.jsonl"),
                        "--retune", str(args.run_dir / "retune.json")]
    try:
        from cacheshift import report
    except ImportError:  # the report (#48) is not merged yet
        print("\nGateway runs written. Make the report with:\n  python -m cacheshift.report " + " ".join(report_args))
        return
    print()
    report.main(report_args)


if __name__ == "__main__":
    main()
