"""Local replay HTTP endpoint. Start with python -m cacheshift.gateway."""

import argparse
import hashlib
import json
from pathlib import Path
import time
from typing import Annotated, Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from cacheshift.replay_gateway import STRONG, ReplayGateway, calibrate, load_dataset
from cacheshift.router import LocalBERTRouter, REVISION

ROOT = Path(__file__).resolve().parents[2]
DATASET = ROOT / "data/replay_demo/questions.jsonl"


class ReplayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question_id: Annotated[str, Field(strict=True, min_length=1)]


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")
    role: Literal["user"]
    content: Annotated[str, Field(strict=True, min_length=1)]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: Literal["cacheshift", STRONG]
    messages: Annotated[list[ChatMessage], Field(min_length=1, max_length=1)]
    stream: Literal[False] = False
    n: Literal[1] = 1


def create_app(gateway):
    app = FastAPI(title="CacheShift replay gateway")
    # Exact full-text matches only: changing context invalidates a recorded answer.
    prompt_ids = {}
    for row in gateway.records.values():
        if row["split"] == "test":
            prompt_ids.setdefault(row["text"], []).append(row["question_id"])

    @app.post("/v1/chat/completions")
    def chat(request: ChatRequest):
        ids = prompt_ids.get(request.messages[0].content, [])
        if len(ids) != 1:
            raise HTTPException(status_code=400, detail="Replay requires one unambiguous exact test prompt")
        event = gateway.answer(ids[0])
        return {
            "id": "chatcmpl-" + event["request_id"], "object": "chat.completion",
            "created": int(time.time()), "model": event["model"],
            "choices": [{"index": 0, "message": {"role": "assistant", "content": event["answer"]},
                         "finish_reason": "stop"}],
            # Token usage is not available in this replay fixture. Do not invent it.
            "usage": None,
            "cacheshift": {key: event[key] for key in ("request_id", "config_id", "cache_hit", "route")},
        }

    @app.get("/health")
    def health():
        return {"status": "ok", "mode": "recorded-answer-replay"}

    @app.get("/config")
    def config():
        return {"config_id": gateway.config_id, **gateway.config}

    @app.get("/questions")
    def questions():
        return [{"question_id": row["question_id"], "text": row["text"]}
                for row in gateway.records.values() if row["split"] == "test"]

    @app.post("/replay")
    def replay(request: ReplayRequest):
        try:
            return gateway.answer(request.question_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=exc.args[0]) from exc

    return app


def prepare(dataset=DATASET, offline=True):
    records = load_dataset(dataset)
    router = LocalBERTRouter(ROOT / "data/cache/routellm", offline=offline)
    calibration = calibrate(records, router, target=0.5)
    digest = hashlib.sha256(Path(dataset).read_bytes()).hexdigest()
    return records, router, calibration, digest


def main():
    import uvicorn

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--download", action="store_true", help="Allow the initial public checkpoint download")
    parser.add_argument("--calibration", type=Path, help="Validated tuning-only artifact from cacheshift.retune")
    args = parser.parse_args()
    args.run_dir.mkdir(parents=True, exist_ok=False)
    records, router, calibration, digest = prepare(args.dataset, offline=not args.download)
    if args.calibration:
        from cacheshift.retune import load_calibration
        calibration = load_calibration(args.calibration, digest, REVISION, records)
    engine = ReplayGateway(records, router, calibration, args.run_dir / "requests.jsonl",
                           dataset_sha256=digest, router_revision=REVISION)
    (args.run_dir / "config.json").write_text(json.dumps({**engine.config, **calibration}, indent=2), encoding="utf-8")
    uvicorn.run(create_app(engine), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
