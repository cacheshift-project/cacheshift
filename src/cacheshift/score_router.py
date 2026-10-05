"""Run: python -m cacheshift.score_router [--offline]."""

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import time

from cacheshift.router import CHECKPOINT, REVISION, UPSTREAM_REVISION, LocalBERTRouter

ROOT = Path(__file__).resolve().parents[2]


def read_questions(path):
    records = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
               if line.strip()]
    if not records:
        raise ValueError("Question file is empty")
    seen = set()
    for row in records:
        if not isinstance(row.get("question_id"), str) or not row["question_id"].strip():
            raise ValueError("Each question needs a nonempty question_id")
        if row["question_id"] in seen:
            raise ValueError("Duplicate question_id")
        if not isinstance(row.get("text"), str) or not row["text"].strip():
            raise ValueError("Each question needs nonempty text")
        seen.add(row["question_id"])
    return records


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "data/router_smoke/questions.jsonl")
    parser.add_argument("--output", type=Path, default=ROOT / "experiments/results/router_smoke.json")
    parser.add_argument("--cache-dir", type=Path, default=ROOT / "data/cache/routellm")
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--threads", type=int, default=4)
    args = parser.parse_args()
    questions = read_questions(args.input)
    start = time.perf_counter()
    router = LocalBERTRouter(args.cache_dir, args.offline, args.threads)
    load_seconds = time.perf_counter() - start
    results = []
    for question in questions:
        start = time.perf_counter()
        result = router.score(question["text"])
        result.update(question_id=question["question_id"],
                      scoring_ms=(time.perf_counter() - start) * 1000)
        results.append(result)
        print(f'{result["question_id"]}: {result["router_score"]:.6f}', flush=True)
    report = {
        "purpose": "CPU feasibility smoke test; not accuracy or budget calibration",
        "checkpoint": CHECKPOINT, "revision": REVISION,
        "upstream_revision": UPSTREAM_REVISION, "device": "cpu", "threads": args.threads,
        "offline": args.offline, "python": platform.python_version(),
        "platform": platform.platform(),
        "packages": {name: importlib.metadata.version(name)
                     for name in ("torch", "transformers", "huggingface-hub", "tokenizers")},
        "input_sha256": hashlib.sha256(args.input.read_bytes()).hexdigest(),
        "load_seconds": load_seconds, "results": results,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {len(results)} scores to {args.output}")


if __name__ == "__main__":
    main()
