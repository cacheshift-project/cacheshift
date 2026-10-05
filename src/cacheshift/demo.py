"""Exercise a real loopback HTTP gateway, with and without exact caching."""

import argparse
from contextlib import contextmanager
import json
from pathlib import Path
import random
import socket
import threading
import time
from urllib.request import Request, urlopen

import uvicorn

from cacheshift.gateway import DATASET, create_app, prepare
from cacheshift.replay_gateway import ReplayGateway, summarize
from cacheshift.router import REVISION


@contextmanager
def serve(app):
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, log_level="error"))
    thread = threading.Thread(target=server.run, kwargs={"sockets": [sock]}, daemon=True)
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError("Replay HTTP server failed to start")
            time.sleep(0.02)
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=10)
        sock.close()
        if thread.is_alive():
            raise RuntimeError("Replay HTTP server did not stop")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--download", action="store_true")
    args = parser.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=False)
    records, router, calibration, digest = prepare(args.dataset, offline=not args.download)
    ids = [row["question_id"] for row in records.values() if row["split"] == "test"]
    rng = random.Random(601)
    stream = ids + rng.choices(ids, k=5)
    rng.shuffle(stream)
    report = {"purpose": "Development pipeline demonstration, not a research estimate",
              "calibration": calibration, "dataset_sha256": digest, "seed": 601,
              "router_revision": REVISION, "stream": stream, "runs": {}}
    for name, cache in (("no_cache", False), ("exact_cache", True)):
        engine = ReplayGateway(records, router, calibration, args.run_dir / f"{name}.jsonl",
                               cache_enabled=cache, dataset_sha256=digest, router_revision=REVISION)
        events = []
        with serve(create_app(engine)) as url:
            for question_id in stream:
                request = Request(url + "/replay", data=json.dumps({"question_id": question_id}).encode(),
                                  headers={"Content-Type": "application/json"}, method="POST")
                with urlopen(request, timeout=120) as response:
                    event = json.load(response)
                events.append(event)
                print(f'{name}: {question_id} -> {event["route"]}', flush=True)
        report["runs"][name] = {"config": engine.config, "summary": summarize(events, 0.5)}
    (args.run_dir / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    lines = ["# Replay gateway demo", "", "Development diagnostic only; no paid model calls.", "",
             "The planned strong-model share is 50% of requests reaching the router.", "",
             "| Mode | Requests | Cache hits | Routed | Strong calls | Strong share of routed | Strong share of all | Historical model cost USD |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]
    for name, run in report["runs"].items():
        s = run["summary"]
        lines.append(f'| {name} | {s["requests"]} | {s["cache_hits"]} | {s["routed_requests"]} | {s["strong_calls"]} | {s["strong_share_of_routed"]:.1%} | {s["strong_share_of_all"]:.1%} | {s["historical_model_cost_usd"]:.6f} |')
    lines += ["", "Costs are recorded historical estimates and exclude CPU/cache overhead. Latencies in logs measure local replay, not model generation.",
              "", "These fixed development traces have no confidence intervals and establish no general drift or quality result. Exact caching cannot test semantic false hits. No retuning is performed."]
    report_text = "\n".join(lines) + "\n"
    (args.run_dir / "report.md").write_text(report_text, encoding="utf-8")
    print(report_text)


if __name__ == "__main__":
    main()
