"""Does the difference check generalize? The MMLU difference-check pipeline, unchanged, on HellaSwag.

    python -m cacheshift.generalization_check --run-dir experiments/results/hellaswag-check-<date>

Implements docs/sprints/Sprint_4/HellaSwag_Generalization_Protocol.md (fixed before any run): no cache,
cache 0.90 and cache 0.90 + difference check 0.80 on every keyed HellaSwag test question plus uniform
repeats, then the safe setting finder on the same traffic. Recorded answers only.
"""

import argparse
import gzip
import hashlib
import json
from pathlib import Path

from cacheshift import setting_finder
from cacheshift.difference_check import stream_runs
from cacheshift.gateway import ROOT
from cacheshift.replay_gateway import calibrate, load_dataset
from cacheshift.retune_scale import SCORES, MemoRouter

DATASET = ROOT / "data/hellaswag_all_20261127/questions.jsonl"
DATASET_SHA = "f516927bd12dfb3da4dcb6bbd9cd27425595eac75d0d15f3fc928add77c665a6"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    args = parser.parse_args(argv)
    from cacheshift.router import LocalBERTRouter
    from cacheshift.semantic_cache import EMBEDDING_MODEL, SentenceEmbedder

    if hashlib.sha256(DATASET.read_bytes()).hexdigest() != DATASET_SHA:
        raise SystemExit("The HellaSwag set differs from the protocol's; rebuild it with tools/build_hellaswag_retune.py")
    args.run_dir.mkdir(parents=True, exist_ok=False)
    router = MemoRouter(LocalBERTRouter(ROOT / "data/cache/routellm", offline=True), SCORES)
    embed = SentenceEmbedder(EMBEDDING_MODEL, cache_dir=str(ROOT / "data/cache/embeddings"))
    results = {"protocol": "docs/sprints/Sprint_4/HellaSwag_Generalization_Protocol.md", "dataset_sha256": DATASET_SHA}
    results["hellaswag"] = stream_runs("hellaswag", DATASET, [(0.90, 0.80)], None, router, embed, args.run_dir)
    records = load_dataset(DATASET)
    with open(args.run_dir / "hellaswag_no_cache.jsonl", encoding="utf-8") as stream:
        order = [json.loads(line)["question_id"] for line in stream]
    results["settings"] = setting_finder.sweep(order, records, router, calibrate(records, router, target=0.5), embed)
    print("Recommended:", results["settings"]["recommended"], flush=True)
    (args.run_dir / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")
    for path in args.run_dir.glob("*.jsonl"):
        with path.open("rb") as source, gzip.open(path.with_suffix(".jsonl.gz"), "wb", compresslevel=9) as target:
            target.write(source.read())
        path.unlink()


if __name__ == "__main__":
    main()
