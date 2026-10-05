"""Run one unchanged SDK app against direct replay and CacheShift addresses."""

import argparse
import json
from pathlib import Path

from cacheshift.chat_client import ask
from cacheshift.demo import serve
from cacheshift.gateway import create_app, prepare
from cacheshift.replay_gateway import ReplayGateway
from cacheshift.router import REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=False)
    records, router, calibration, digest = prepare()
    prompt = next(row["text"] for row in records.values() if row["split"] == "test")
    (args.run_dir / "prompt.txt").write_text(prompt, encoding="utf-8")
    report = {"mode": "local replay, no live provider", "runs": {}}
    for name, cut, cache in (("direct_recorded_strong", {**calibration, "threshold": 0.0,
                                                       "target_strong_share": 1.0}, False),
                              ("cacheshift", calibration, True)):
        engine = ReplayGateway(records, router, cut, args.run_dir / f"{name}.jsonl",
                               cache_enabled=cache, dataset_sha256=digest, router_revision=REVISION)
        with serve(create_app(engine)) as url:
            results = [ask(url + "/v1", prompt) for _ in range(2)]
        report["runs"][name] = [{"id": r.id, "model": r.model,
                                 "answer": r.choices[0].message.content} for r in results]
    (args.run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
