"""Sprint 3 demo (#50): a question stream through the live gateway, then the one-page report.

Starts the replay gateway's HTTP server twice on this machine, once with no cache and once with
the semantic cache (#47), and sends the same question stream to each: every ARC holdout test
question once plus uniform repeats (Story 2's rule, seed 601). Then it writes the one-page report
(#48), comparing the cached run against the no-cache run of the same stream, so the cache's own
effect on cost, accuracy and expensive-model share is separated from the router's cutoff.

    python -m cacheshift.sprint3_demo --run-dir experiments/results/sprint3-demo-<date> [--threshold 0.90]

Runs on a laptop CPU in about 3 minutes; no API calls (recorded answers).
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


def run(records, router, calibration, digest, embed, stream, run_dir, threshold):
    report = {"purpose": "Sprint 3 demo (#50): same question stream through the live gateway with and without the cache",
              "dataset_sha256": digest, "seed": SEED, "router_revision": REVISION,
              "calibration": {key: calibration[key] for key in ("target_strong_share", "threshold", "tuning_strong_share")},
              "requests": len(stream), "unique_questions": len(set(stream)), "runs": {}}
    for name, options in (("no_cache", {"cache_enabled": False}),
                          (f"semantic_{threshold:.2f}", {"semantic_threshold": threshold, "embed": embed})):
        engine = ReplayGateway(records, router, calibration, run_dir / f"{name}.jsonl", dataset_sha256=digest,
                               router_revision=REVISION, **options)
        with serve(create_app(engine)) as url:
            events = send(url, stream, name)
        report["runs"][name] = {"config": engine.config, "config_id": engine.config_id,
                                "summary": summarize(events, calibration["target_strong_share"])}
    (run_dir / "runs.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--threshold", type=float, default=0.90, help="Semantic cache setting (cosine similarity)")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/cache/embeddings")
    args = parser.parse_args()
    from cacheshift.semantic_cache import SentenceEmbedder

    args.run_dir.mkdir(parents=True, exist_ok=False)
    records, router, calibration, digest = prepare(args.dataset)
    test = {qid: row for qid, row in records.items() if row["split"] == "test"}
    embed = SentenceEmbedder(EMBEDDING_MODEL, cache_dir=str(args.cache_dir))
    embed.warm(row["text"] for row in test.values())
    stream = request_stream(test, SEED)
    print(f"Sending {len(stream)} requests ({len(test)} questions plus repeats) to the gateway, twice", flush=True)
    run(records, router, calibration, digest, embed, stream, args.run_dir, args.threshold)

    cached = args.run_dir / f"semantic_{args.threshold:.2f}.jsonl"
    report_args = ["--log", str(cached), "--fresh-log", str(args.run_dir / "no_cache.jsonl"),
                   "--dataset", str(args.dataset), "--config", str(args.run_dir / "runs.json"),
                   "--out", str(args.run_dir / "report.html")]
    try:
        from cacheshift import report
    except ImportError:  # the report (#48) is not merged yet
        print("\nGateway runs written. Make the report with:\n  python -m cacheshift.report " + " ".join(report_args))
        return
    print()
    report.main(report_args)


if __name__ == "__main__":
    main()
