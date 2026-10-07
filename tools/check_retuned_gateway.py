"""Verify a saved retuning artifact through the actual local SDK endpoint."""

import argparse
import hashlib
import json
from pathlib import Path

from cacheshift.chat_client import ask
from cacheshift.demo import serve
from cacheshift.gateway import ROOT, create_app
from cacheshift.replay_gateway import ReplayGateway, load_dataset
from cacheshift.retune import load_calibration
from cacheshift.router import LocalBERTRouter, REVISION


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--calibration", type=Path, required=True)
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args()
    records = load_dataset(args.dataset)
    digest = hashlib.sha256(args.dataset.read_bytes()).hexdigest()
    calibration = load_calibration(args.calibration, digest, REVISION, records)
    args.run_dir.mkdir(parents=True, exist_ok=False)
    router = LocalBERTRouter(ROOT / "data/cache/routellm", offline=True)
    gateway = ReplayGateway(records, router, calibration, args.run_dir / "requests.jsonl",
                            dataset_sha256=digest, router_revision=REVISION)
    row = next(row for row in records.values() if row["split"] == "test")
    with serve(create_app(gateway)) as url:
        responses = [ask(url + "/v1", row["text"]) for _ in range(2)]
    events = [json.loads(line) for line in gateway.log_path.read_text().splitlines()]
    fields = {"request_id", "timestamp", "question_id", "config_id", "cache_hit",
              "similarity", "matched_question_id", "router_score", "route", "model",
              "answer", "cost_usd", "latency_ms"}
    assert len(events) == 2 and all(fields <= event.keys() for event in events)
    assert events[0]["cache_hit"] is False and events[1]["cache_hit"] is True
    assert events[1]["route"] == "cache" and events[1]["cost_usd"] == 0
    expected = "strong" if events[0]["router_score"] >= calibration["threshold"] else "weak"
    assert events[0]["route"] == expected
    assert gateway.config["threshold"] == calibration["threshold"]
    for response, event in zip(responses, events):
        assert response.model == event["model"]
        assert response.choices[0].message.content == event["answer"] == row["answers"][event["model"]]["answer"]
    report = {"scope": "Saved-cutoff local replay integration; two requests, not a share estimate",
              "dataset_sha256": digest, "calibration_sha256": hashlib.sha256(args.calibration.read_bytes()).hexdigest(),
              "router_revision": REVISION, "threshold": calibration["threshold"],
              "target": calibration["target_strong_share"], "question_id": row["question_id"],
              "config_id": gateway.config_id, "routes": [event["route"] for event in events],
              "answers": [event["answer"] for event in events], "required_log_fields_verified": True}
    (args.run_dir / "report.json").write_bytes((json.dumps(report, indent=2) + "\n").encode())
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
