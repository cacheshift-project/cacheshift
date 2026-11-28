"""Which cache setting is safe for your questions? Replay your own traffic at each setting.

    python -m cacheshift.setting_finder --log run/no_cache.jsonl --dataset data/... --out run/settings.json
    python -m cacheshift.report --log run/semantic_0.90.jsonl ... --settings run/settings.json --out run/report.html

The request stream in a gateway log (any run: the question order is what matters) is sent again
through ReplayGateway at each match setting, with and without the difference check, plus no cache.
For each: how often the cache answers, how many answers the cache made wrong (another question's
saved answer, wrong for this one), accuracy against the no-cache run, and cost per 1,000 requests,
with 95% ranges over question groups. The recommendation is the setting that answers the most
from the cache while the top of its wrong-answer range stays at or under --limit (default 0.5%,
1 in 200 answers). Recorded answers only.
"""

import argparse
import hashlib
import json
from pathlib import Path
import tempfile

from cacheshift import report
from cacheshift.gateway import ROOT
from cacheshift.replay_gateway import ReplayGateway, calibrate, load_dataset
from cacheshift.router import REVISION

SETTINGS = (0.95, 0.90, 0.85, 0.80)
CHECKS = (None, 0.80)
LIMIT = 0.005


def label(setting, check):
    return "no cache" if setting is None else f"{setting:.2f}" + ("" if check is None else " + difference check")


def sweep(stream, records, router, calibration, embed, limit=LIMIT, settings=SETTINGS, checks=CHECKS, samples=1000):
    work = Path(tempfile.mkdtemp(prefix="cacheshift-settings-"))

    def run(name, **options):
        engine = ReplayGateway(records, router, calibration, work / f"{name}.jsonl", router_revision=REVISION, **options)
        return [engine.answer(qid) for qid in stream]

    fresh = run("no_cache", cache_enabled=False)
    rows = []
    for setting in settings:
        for check in checks:
            events = run(f"{setting}_{check}", semantic_threshold=setting, embed=embed, semantic_verify=check)
            built = report.build(events, records, calibration["target_strong_share"], fresh_events=fresh,
                                 samples=samples)
            r, t = built["rates"], built["totals"]
            rows.append({"setting": setting, "difference_check": check, "label": label(setting, check),
                         "hit_rate": r["hit_rate"], "wrong_caused": t["wrong_question_wrong"],
                         "wrong_caused_rate": r["wrong_question_wrong_rate"], "usd_per_1000": r["usd_per_1000"],
                         "accuracy_change_vs_fresh": built["paired"]["accuracy_change"],
                         "share": r["strong_share_of_routed"]})
    fresh_rates = report.build(fresh, records, calibration["target_strong_share"], samples=samples)["rates"]
    safe = [row for row in rows if row["wrong_caused_rate"]["ci95"][1] is not None
            and row["wrong_caused_rate"]["ci95"][1] <= limit + 1e-12]
    best = max(safe, key=lambda row: (row["hit_rate"]["estimate"], -row["wrong_caused_rate"]["estimate"]), default=None)
    return {"requests": len(stream), "limit": limit, "rows": rows,
            "no_cache": {"usd_per_1000": fresh_rates["usd_per_1000"], "accuracy": fresh_rates["accuracy"]},
            "recommended": None if best is None else best["label"]}


def main(argv=None):
    from cacheshift.retune_scale import SCORES, MemoRouter
    from cacheshift.router import LocalBERTRouter
    from cacheshift.semantic_cache import EMBEDDING_MODEL, SentenceEmbedder

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--log", type=Path, required=True, help="A gateway log of your traffic (its question order is used)")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--limit", type=float, default=LIMIT,
                        help="Most wrong answers the cache may cause, as a share of requests (default 0.005)")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    records = load_dataset(args.dataset)
    stream = [event["question_id"] for event in report.read_log(args.log)]
    router = MemoRouter(LocalBERTRouter(ROOT / "data/cache/routellm", offline=True), SCORES)
    calibration = calibrate(records, router, target=0.5)
    embed = SentenceEmbedder(EMBEDDING_MODEL, cache_dir=str(ROOT / "data/cache/embeddings"))
    embed.warm(records[qid]["text"] for qid in set(stream))
    result = sweep(stream, records, router, calibration, embed, limit=args.limit)
    result.update(log=args.log.name, dataset_sha256=hashlib.sha256(args.dataset.read_bytes()).hexdigest())
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    for row in result["rows"]:
        print(f"{row['label']:>26}: from cache {report.pct(row['hit_rate']['estimate'])}, wrong caused "
              f"{row['wrong_caused']} ({report.rng(row['wrong_caused_rate'], lambda v: report.pct(v, 2))}), "
              f"{report.money(row['usd_per_1000']['estimate'])} per 1,000")
    print(f"Recommended (wrong answers caused at most {report.pct(args.limit, 1)}): {result['recommended'] or 'no cache'}")


if __name__ == "__main__":
    main()
