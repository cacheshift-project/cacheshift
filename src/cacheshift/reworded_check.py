"""Reworded repeats: how many does the semantic cache catch, and how often does it match the wrong question?

    python -m cacheshift.reworded_check --out experiments/results/reworded-<date>

Every MMLU test question (data/mmlu_all_20261127) is put in the semantic cache, as if each had been
asked once. Then 120 reworded versions (data/reworded_20261127/rewordings.jsonl: the question
reworded, the answer options unchanged) are looked up at each match setting. A lookup either
catches the reworded question's own original (a saving the exact cache misses), matches a
different question (a wrong-question hit, scored against the answer key), or misses.

Two embeddings: the full prompt the gateway stores (instruction, question and options), and the
question text only, closer to how a chatbot user asks. Results count only after the rewordings
pass the hand check in #7 (at least 95% keep their meaning). No model calls: a miss would need a
live answer, so accuracy on misses is not measured here.
"""

import argparse
import json
from pathlib import Path
import re

import numpy as np

from cacheshift.gateway import ROOT
from cacheshift.replay_gateway import load_dataset
from cacheshift.report import is_correct
from cacheshift.retune_scale import DATASET

REWORDINGS = ROOT / "data/reworded_20261127/rewordings.jsonl"
SETTINGS = (0.95, 0.90, 0.85, 0.80)


def stem_of(prompt):
    body = prompt.split("\n\n", 1)[1].split("\nPrint only", 1)[0]
    return re.split(r"\nA\) ", body)[0]


def reworded_prompt(prompt, original_stem, new_stem):
    if prompt.count(original_stem) != 1:
        raise ValueError("The original question text must appear exactly once in its prompt")
    return prompt.replace(original_stem, new_stem)


def check(records, rewordings, embed_many, view):
    """Cache = every test question; look up each rewording. view(prompt) -> text that is embedded."""
    test = sorted((row for row in records.values() if row["split"] == "test"), key=lambda r: r["question_id"])
    keys = [view(row["text"]) for row in test]
    matrix = embed_many(keys)
    queries = []
    for item in rewordings:
        row = records[item["question_id"]]
        queries.append(view(reworded_prompt(row["text"], item["original"], item["reworded"])))
    sims = embed_many(queries) @ matrix.T
    position = {row["question_id"]: i for i, row in enumerate(test)}
    out = {"items": [], "by_setting": {}}
    for item, row_sims in zip(rewordings, sims):
        own = position[item["question_id"]]
        best = int(np.argmax(row_sims))
        out["items"].append({"question_id": item["question_id"], "level": item["level"],
                             "own_similarity": float(row_sims[own]), "best_similarity": float(row_sims[best]),
                             "best_is_own": best == own, "best_question_id": test[best]["question_id"]})
    for setting in SETTINGS:
        caught = wrong_question = wrong_answer = 0
        for item, result in zip(rewordings, out["items"]):
            if result["best_similarity"] < setting:
                continue
            if result["best_is_own"]:
                caught += 1
            else:
                wrong_question += 1
                served = records[result["best_question_id"]]["answers"]
                # the cache would serve whatever model answered the matched question; check both
                gold_row = records[item["question_id"]]
                wrong_answer += not all(is_correct(gold_row, served[m]["answer"]) for m in served)
        n = len(rewordings)
        out["by_setting"][f"{setting:.2f}"] = {"caught_own_original": caught, "matched_other_question": wrong_question,
                                               "other_question_possibly_wrong": wrong_answer,
                                               "missed": n - caught - wrong_question, "n": n}
    own = np.array([r["own_similarity"] for r in out["items"]])
    out["own_similarity"] = {"median": float(np.median(own)), "p10": float(np.percentile(own, 10)),
                             "p90": float(np.percentile(own, 90)), "min": float(own.min())}
    return out


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dataset", type=Path, default=DATASET)
    parser.add_argument("--rewordings", type=Path, default=REWORDINGS)
    args = parser.parse_args(argv)
    from sentence_transformers import SentenceTransformer
    from cacheshift.semantic_cache import EMBEDDING_MODEL

    model = SentenceTransformer(EMBEDDING_MODEL, device="cpu", cache_folder=str(ROOT / "data/cache/embeddings"))
    embed_many = lambda texts: model.encode(list(texts), batch_size=64, normalize_embeddings=True,
                                            convert_to_numpy=True, show_progress_bar=False).astype(np.float32)
    records = load_dataset(args.dataset)
    rewordings = [json.loads(line) for line in args.rewordings.read_text(encoding="utf-8").splitlines() if line.strip()]
    checked = [r for r in rewordings if r.get("same_meaning") is not None]
    results = {"rewordings": len(rewordings), "hand_checked": len(checked),
               "hand_check_pass_rate": (sum(bool(r["same_meaning"]) for r in checked) / len(checked)) if checked else None,
               "note": "Counts only after the #7 hand check (>= 95% keep their meaning).",
               "views": {}}
    for name, view in (("full prompt (as the gateway stores it)", lambda text: text),
                       ("question only", stem_of)):
        results["views"][name] = check(records, rewordings, embed_many, view)
        print(name, json.dumps(results["views"][name]["by_setting"]), json.dumps(results["views"][name]["own_similarity"]),
              flush=True)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "results.json").write_text(json.dumps(results, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
