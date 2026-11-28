"""Live demo dashboard: watch questions go through the gateway one at a time.

    python -m cacheshift.dashboard            # then open http://127.0.0.1:8050

Each question in the Sprint 3 stream (the ARC holdout test questions plus uniform repeats) is sent
through a real ReplayGateway with the cache and router inside it: the same object the HTTP gateway
and the Sprint 3 demo use, writing the same request log. The page shows where each question went
(answered from the cache, the cheap model or the expensive model), whether the answer was right,
when the cache gave a question another question's answer, and running cost, accuracy and
expensive-model share against the plan. The match setting (off, 0.95, 0.90, 0.80) starts a fresh
run with an empty cache. At the end, the one-page report (#48) is made from that run's log.

Recorded answers only (no model API calls), so it works offline once the router and embedding
model are downloaded (pass --download the first time).
"""

import argparse
from datetime import datetime
import itertools
import math
from pathlib import Path
import threading

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, ConfigDict, Field

from cacheshift import report
from cacheshift.cache_quality import request_stream
from cacheshift.gateway import ROOT
from cacheshift.replay_gateway import STRONG, WEAK, ReplayGateway, calibrate, load_dataset, validated_score
from cacheshift.router import REVISION

DATASET = ROOT / "data/retune_holdout_20261007/questions.jsonl"
PAGE = Path(__file__).with_name("dashboard_page.html")
SETTINGS = {"off": None, "0.95": 0.95, "0.90": 0.90, "0.80": 0.80}
SEED = 601
MAX_STEP = 50


class MemoRouter:
    """The real router, scoring each question text once (single-question scoring, as the gateway does)."""

    def __init__(self, router):
        self.router, self.scores, self.lock = router, {}, threading.Lock()

    def score(self, text):
        with self.lock:
            if text not in self.scores:
                self.scores[text] = validated_score(self.router, text)
            return {"router_score": self.scores[text]}


def split_question(text):
    """(question, options) for display: drops the answer-format instruction the models were given."""
    lines = [line.strip() for line in text.strip().splitlines() if line.strip()]
    lines = [line for line in lines if not line.startswith(("Print only", "Please answer with the letter")) and line != "Answer:"]
    options = [line for line in lines if len(line) > 2 and line[0] in "ABCDE" and line[1] == ")"]
    stem = " ".join(line for line in lines if line not in options)
    return stem, options


def wilson(successes, n, z=1.96):
    """Rough 95% range for a share; the report uses a group bootstrap instead."""
    if n == 0:
        return None, None
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return max(0.0, centre - half), min(1.0, centre + half)


class Session:
    def __init__(self, number, setting, records, test, router, calibration, digest, embed, run_dir, seed):
        threshold = SETTINGS[setting]
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.log_path = run_dir / f"{stamp}-{number:03d}-{'no-cache' if threshold is None else f'semantic-{setting}'}.jsonl"
        options = {"cache_enabled": False} if threshold is None else {"semantic_threshold": threshold, "embed": embed}
        self.engine = ReplayGateway(records, router, calibration, self.log_path, dataset_sha256=digest,
                                    router_revision=REVISION, seed=seed, **options)
        self.records, self.router, self.calibration = records, router, calibration
        self.setting, self.threshold = setting, threshold
        self.stream = request_stream(test, seed)
        self.position, self.events = 0, []
        self.lock = threading.Lock()
        self.totals = dict(requests=0, hits=0, routed=0, strong=0, weak=0, correct=0, cost=0.0,
                           no_cache_cost=0.0, all_strong_cost=0.0, wrong_question=0, wrong_question_wrong=0,
                           repeated_wrong=0)

    def describe(self):
        return {"setting": self.setting, "threshold": self.threshold, "total": len(self.stream),
                "position": self.position, "plan": self.calibration["target_strong_share"],
                "cutoff": self.calibration["threshold"], "band": report.DRIFT_BAND, "log": self.log_path.name,
                "totals": self.summary()}

    def summary(self):
        t = self.totals
        low, high = wilson(t["strong"], t["routed"])
        share = t["strong"] / t["routed"] if t["routed"] else None
        plan, band = self.calibration["target_strong_share"], report.DRIFT_BAND
        if share is None:
            verdict = "waiting"
        elif low >= plan - band and high <= plan + band:
            verdict = "within"
        elif high < plan - band or low > plan + band:
            verdict = "outside"
        else:
            verdict = "too-few"
        per_1000 = lambda cost: 1000 * cost / t["requests"] if t["requests"] else None
        return {**t, "accuracy": t["correct"] / t["requests"] if t["requests"] else None,
                "share": share, "share_low": low, "share_high": high, "share_verdict": verdict,
                "usd_per_1000": per_1000(t["cost"]), "no_cache_usd_per_1000": per_1000(t["no_cache_cost"]),
                "all_strong_usd_per_1000": per_1000(t["all_strong_cost"]),
                "wrong_from_cache": t["wrong_question_wrong"] + t["repeated_wrong"]}

    def step(self, count):
        with self.lock:
            out = []
            for _ in range(count):
                if self.position >= len(self.stream):
                    break
                question_id = self.stream[self.position]
                self.position += 1
                event = self.engine.answer(question_id)
                self.events.append(event)
                out.append(self.describe_event(event))
            return {"events": out, "position": self.position, "total": len(self.stream),
                    "done": self.position >= len(self.stream), "totals": self.summary()}

    def describe_event(self, event):
        row = self.records[event["question_id"]]
        correct, wrong_question, repeated_wrong = report.classify(event, self.records)
        # What the same request would have cost with no cache: the router's pick for this question.
        fresh_route = "strong" if self.router.score(row["text"])["router_score"] >= self.calibration["threshold"] else "weak"
        fresh_model = STRONG if fresh_route == "strong" else WEAK
        t = self.totals
        t["requests"] += 1
        t["hits"] += event["cache_hit"]
        t["routed"] += not event["cache_hit"]
        t["strong"] += event["route"] == "strong"
        t["weak"] += event["route"] == "weak"
        t["correct"] += correct
        t["cost"] += event["cost_usd"]
        t["no_cache_cost"] += row["answers"][fresh_model]["cost_usd"]
        t["all_strong_cost"] += row["answers"][STRONG]["cost_usd"]
        t["wrong_question"] += wrong_question
        t["wrong_question_wrong"] += wrong_question and not correct
        t["repeated_wrong"] += repeated_wrong
        matched = self.records.get(event["matched_question_id"]) if wrong_question else None
        stem, options = split_question(row["text"])
        return {"n": self.position, "question_id": event["question_id"], "text": stem, "options": options,
                "route": event["route"], "cache_hit": event["cache_hit"], "similarity": event["similarity"],
                "router_score": event["router_score"], "answer": report.first_line(str(event["answer"]), 40),
                "gold": row["gold_answer"], "correct": correct, "cost": event["cost_usd"],
                "wrong_question": wrong_question, "repeated_wrong": repeated_wrong,
                "matched_text": split_question(matched["text"])[0] if matched else None}

    def report_html(self):
        with self.lock:
            if not self.events:
                raise ValueError("Send some questions first")
            built = report.build(list(self.events), self.records, self.calibration["target_strong_share"])
            built["run"] = {"config_id": self.engine.config_id, "config": self.engine.config, "log": self.log_path.name}
            name = "no cache" if self.threshold is None else f"cache at {self.setting}"
            return report.render_html(built, f"CacheShift live demo, {name}", self.log_path.name)


class NewSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    setting: str = "0.90"
    seed: int = SEED


class Step(BaseModel):
    model_config = ConfigDict(extra="forbid")
    count: int = Field(1, ge=1, le=MAX_STEP)


def create_app(records, router, calibration, digest, embed, run_dir):
    app = FastAPI(title="CacheShift live dashboard")
    test = {qid: row for qid, row in records.items() if row["split"] == "test"}
    sessions, numbers, lock = {}, itertools.count(1), threading.Lock()

    def get(session_id):
        session = sessions.get(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="That run has ended; start a new one")
        return session

    @app.get("/", response_class=HTMLResponse)
    def page():
        return PAGE.read_text(encoding="utf-8")

    @app.post("/api/session")
    def new_session(request: NewSession):
        if request.setting not in SETTINGS:
            raise HTTPException(status_code=400, detail=f"Match setting must be one of {', '.join(SETTINGS)}")
        if request.setting != "off" and embed is None:
            raise HTTPException(status_code=400, detail="Started with --no-cache-model; only 'off' is available")
        with lock:
            number = next(numbers)
            session = Session(number, request.setting, records, test, router, calibration, digest, embed,
                              run_dir, request.seed)
            sessions.clear()  # one run at a time keeps memory flat at a poster table
            sessions[str(number)] = session
        return {"id": str(number), **session.describe()}

    @app.post("/api/session/{session_id}/step")
    def step(session_id: str, request: Step):
        return get(session_id).step(request.count)

    @app.get("/api/session/{session_id}/report", response_class=HTMLResponse)
    def one_page_report(session_id: str):
        try:
            return get(session_id).report_html()
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    return app


def prepare(dataset, offline, with_cache=True):
    import hashlib

    from cacheshift.router import LocalBERTRouter
    from cacheshift.semantic_cache import EMBEDDING_MODEL, SentenceEmbedder

    records = load_dataset(dataset)
    router = MemoRouter(LocalBERTRouter(ROOT / "data/cache/routellm", offline=offline))
    print("Setting the router's cutoff on the tuning questions...", flush=True)
    calibration = calibrate(records, router, target=0.5)
    test = [row["text"] for row in records.values() if row["split"] == "test"]
    print(f"Scoring {len(test)} test questions once so routing is instant...", flush=True)
    for text in test:
        router.score(text)
    embed = None
    if with_cache:
        if offline:
            import os
            os.environ.setdefault("HF_HUB_OFFLINE", "1")
        embed = SentenceEmbedder(EMBEDDING_MODEL, cache_dir=str(ROOT / "data/cache/embeddings"))
        embed.warm(test)
    return records, router, calibration, hashlib.sha256(Path(dataset).read_bytes()).hexdigest(), embed


def main(argv=None):
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--port", type=int, default=8050)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--run-dir", type=Path, default=ROOT / "experiments/results/dashboard-runs",
                        help="Where each run's request log is written")
    parser.add_argument("--download", action="store_true", help="Allow downloading the router and embedding model")
    parser.add_argument("--no-cache-model", action="store_true", help="Skip the embedding model (cache 'off' only)")
    args = parser.parse_args(argv)
    args.run_dir.mkdir(parents=True, exist_ok=True)
    records, router, calibration, digest, embed = prepare(args.dataset, offline=not args.download,
                                                          with_cache=not args.no_cache_model)
    print(f"Ready: open http://127.0.0.1:{args.port}  (request logs go to {args.run_dir})", flush=True)
    uvicorn.run(create_app(records, router, calibration, digest, embed, args.run_dir),
                host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
