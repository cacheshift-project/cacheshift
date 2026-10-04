"""Replay-only gateway core. Routing never reads answers or correctness labels."""

from datetime import datetime, timezone
import hashlib
import json
import math
from pathlib import Path
import threading
import time
import uuid

STRONG = "gpt-4-1106-preview"
WEAK = "mistralai/mixtral-8x7b-chat"


def load_dataset(path):
    records = {}
    group_splits = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        for field in ("question_id", "group_id", "text", "source"):
            if not isinstance(row.get(field), str) or not row[field].strip():
                raise ValueError(f"Missing or invalid {field}")
        if row["question_id"] in records:
            raise ValueError("Duplicate question_id")
        if row.get("split") not in ("tuning", "test"):
            raise ValueError("split must be tuning or test")
        if row.get("is_original") is not True:
            raise ValueError("This replay backend accepts recorded originals only")
        group = row["group_id"]
        if group in group_splits and group_splits[group] != row["split"]:
            raise ValueError("A question group crosses tuning/test splits")
        group_splits[group] = row["split"]
        for model in (STRONG, WEAK):
            result = row.get("answers", {}).get(model, {})
            if not isinstance(result.get("answer"), str) or not result["answer"].strip():
                raise ValueError(f"Missing recorded answer for {model}")
            cost = result.get("cost_usd")
            if isinstance(cost, bool) or not isinstance(cost, (int, float)) or not math.isfinite(cost) or cost < 0:
                raise ValueError("Recorded cost must be finite and nonnegative")
        records[row["question_id"]] = row
    if not records or {row["split"] for row in records.values()} != {"tuning", "test"}:
        raise ValueError("Dataset must contain tuning and test questions")
    return records


def validated_score(router, text):
    score = float(router.score(text)["router_score"])
    if not math.isfinite(score) or not 0 <= score <= 1:
        raise ValueError("Router score must be finite and between zero and one")
    return score


def calibrate(records, router, target=0.5):
    """Choose attainable tuning share nearest target; ties prefer fewer strong calls."""
    if not math.isfinite(target) or not 0 <= target <= 1:
        raise ValueError("target must be between zero and one")
    tuning = [row for row in records.values() if row["split"] == "tuning"]
    if not tuning:
        raise ValueError("No tuning questions")
    scores = [validated_score(router, row["text"]) for row in tuning]
    # Above 1 supports zero strong calls even when a score is exactly one.
    candidates = sorted(set([0.0, math.nextafter(1.0, math.inf), *scores]))
    threshold = min(candidates, key=lambda cut: (
        abs(sum(score >= cut for score in scores) / len(scores) - target),
        sum(score >= cut for score in scores), -cut,
    ))
    return {
        "target_strong_share": target, "threshold": threshold,
        "tuning_strong_share": sum(score >= threshold for score in scores) / len(scores),
        "tuning_scores": [{"question_id": row["question_id"], "score": score}
                          for row, score in zip(tuning, scores)],
    }


class ReplayGateway:
    def __init__(self, records, router, calibration, log_path, cache_enabled=True,
                 dataset_sha256="", router_revision="", seed=601, repeats=5):
        self.records = records
        self.router = router
        self.threshold = calibration["threshold"]
        self.cache_enabled = cache_enabled
        self.cache = {}
        self.lock = threading.Lock()
        self.config = {
            "mode": "recorded-answer-replay", "cache": "exact" if cache_enabled else "none",
            "target_strong_share": calibration["target_strong_share"],
            "threshold": self.threshold, "dataset_sha256": dataset_sha256,
            "router_revision": router_revision, "seed": seed, "extra_repeats": repeats,
            "strong_model": STRONG, "weak_model": WEAK,
        }
        self.config_id = hashlib.sha256(json.dumps(self.config, sort_keys=True).encode()).hexdigest()[:16]
        self.log_path = Path(log_path)
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        # Each gateway instance starts a new log and empty cache. Never overwrite a run.
        with self.log_path.open("x", encoding="utf-8"):
            pass

    def answer(self, question_id):
        start = time.perf_counter()
        with self.lock:
            row = self.records.get(question_id)
            if row is None or row["split"] != "test":
                raise KeyError("Unknown test question; arbitrary prompts and tuning IDs are not served")
            key = (question_id, row["text"])
            cached = self.cache.get(key) if self.cache_enabled else None
            hit = cached is not None
            if hit:
                model, answer = cached
                score, cost, route = None, 0.0, "cache"
            else:
                score = validated_score(self.router, row["text"])
                route = "strong" if score >= self.threshold else "weak"
                model = STRONG if route == "strong" else WEAK
                outcome = row["answers"][model]
                answer, cost = outcome["answer"], outcome["cost_usd"]
            event = {
                "request_id": str(uuid.uuid4()),
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "question_id": question_id, "config_id": self.config_id,
                "cache_hit": hit, "similarity": 1.0 if hit else None,
                "matched_question_id": question_id if hit else None,
                "router_score": score, "route": route, "model": model,
                "answer": answer, "cost_usd": cost,
                "latency_ms": (time.perf_counter() - start) * 1000,
                "cost_kind": "historical_model_estimate",
                "latency_kind": "local_replay_not_model_generation",
            }
            with self.log_path.open("a", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(event, allow_nan=False) + "\n")
            if not hit and self.cache_enabled:
                self.cache[key] = (model, answer)
            return event


def summarize(events, target):
    total = len(events)
    hits = sum(row["cache_hit"] for row in events)
    calls = total - hits
    strong = sum(row["route"] == "strong" for row in events)
    return {
        "requests": total, "cache_hits": hits, "routed_requests": calls,
        "strong_calls": strong, "planned_strong_share": target,
        "strong_share_of_routed": strong / calls if calls else None,
        "strong_share_of_all": strong / total if total else None,
        "historical_model_cost_usd": sum(row["cost_usd"] for row in events),
    }
