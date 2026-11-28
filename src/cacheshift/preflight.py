"""Is this laptop ready to run the demo offline? Checks everything in seconds and says how to fix it.

    python -m cacheshift.preflight [--dataset data/mmlu_all_20261127/questions.jsonl]

Checks: Python and packages, the router and similarity model downloaded (no internet needed),
the question set, how many of its questions already have a saved router score (else the first
start scores them), and that the dashboard's port is free. Loads nothing heavy.
"""

import argparse
import hashlib
import importlib.util
import json
import socket
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT = ROOT / "data/retune_holdout_20261007/questions.jsonl"
SCORES = ROOT / "data/cache/router_scores.jsonl"
ROUTER_DIR = ROOT / "data/cache/routellm"
EMBED_DIR = ROOT / "data/cache/embeddings"
BUILD_HINTS = {
    "mmlu_all_20261127": "python tools/build_mmlu_retune.py --routerbench data/raw/routerbench_0shot.pkl --download-keys --all-families --output data/mmlu_all_20261127",
    "hellaswag_all_20261127": "python tools/build_hellaswag_retune.py --routerbench data/raw/routerbench_0shot.pkl --download-keys --output data/hellaswag_all_20261127",
}


def check(dataset, port=8050):
    results = []

    def add(ok, what, fix=""):
        results.append((ok, what, fix))

    add(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}", "Install Python 3.12")
    for module, package in (("torch", "torch (CPU)"), ("transformers", "transformers"), ("sentence_transformers", "sentence-transformers"),
                            ("fastapi", "fastapi"), ("uvicorn", "uvicorn"), ("numpy", "numpy")):
        add(importlib.util.find_spec(module) is not None, f"Package {package}",
            "pip install --index-url https://download.pytorch.org/whl/cpu torch" if module == "torch"
            else 'pip install -r requirements-router.txt -e ".[cache]"')
    router_ok = any(ROUTER_DIR.glob("**/model.safetensors"))
    add(router_ok, "Router model downloaded", "python -m cacheshift.dashboard --download   (once, with internet)")
    embed_ok = any(EMBED_DIR.glob("**/config_sentence_transformers.json")) or any(EMBED_DIR.glob("**/modules.json"))
    add(embed_ok, "Similarity model downloaded", "python -m cacheshift.dashboard --download   (once, with internet)")
    dataset = Path(dataset)
    if not dataset.exists():
        add(False, f"Question set {dataset.relative_to(ROOT) if dataset.is_relative_to(ROOT) else dataset}",
            BUILD_HINTS.get(dataset.parent.name, "Build it with the tool named in docs/sprints/Sprint_4/Sprint4_Experiment_Results.md"))
    else:
        texts = [json.loads(line)["text"] for line in dataset.read_text(encoding="utf-8").splitlines() if line.strip()]
        add(True, f"Question set {dataset.name} in {dataset.parent.name} ({len(texts):,} questions)")
        saved = set()
        import gzip
        for source in (ROOT / "data/router_scores_20261127.jsonl.gz", SCORES):
            if source.exists():
                opener = gzip.open if source.suffix == ".gz" else open
                with opener(source, "rt", encoding="utf-8") as stream:
                    saved.update(json.loads(line)["sha256"] for line in stream)
        have = sum(hashlib.sha256(t.encode("utf-8")).hexdigest() in saved for t in texts)
        share = have / len(texts) if texts else 1
        add(share >= 0.99, f"Router scores saved for {have:,} of {len(texts):,} questions",
            "The first dashboard start scores the rest (a few minutes to half an hour); start it once before the demo")
    with socket.socket() as sock:
        free = sock.connect_ex(("127.0.0.1", port)) != 0
    add(free, f"Port {port} free", f"Something is already on port {port}: close it, or start the dashboard with --port 8051")
    return results


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dataset", type=Path, default=DEFAULT)
    parser.add_argument("--port", type=int, default=8050)
    args = parser.parse_args(argv)
    results = check(args.dataset, args.port)
    for ok, what, fix in results:
        print(f"  {'OK ' if ok else 'FIX'}  {what}" + ("" if ok or not fix else f"\n        -> {fix}"))
    ready = all(ok for ok, _, _ in results)
    print("\nReady for the demo." if ready else "\nNot ready yet: do the steps marked FIX above.")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
