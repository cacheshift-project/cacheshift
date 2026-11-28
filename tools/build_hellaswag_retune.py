"""Build the keyed HellaSwag replay set used by the difference-check generalization test.

    python tools/build_hellaswag_retune.py --routerbench data/raw/routerbench_0shot.pkl \
        --download-keys --output data/hellaswag_all_20261127

Every RouterBench HellaSwag row (hellaswag.val.N = HellaSwag validation item N) is checked against
the official validation set (pinned revision and SHA-256): its context and all four endings must
match after whitespace normalisation. RouterBench shows the endings in its own order, so the key is
the letter of the official correct ending as shown. Groups are HellaSwag's source_id (one video or
article); groups ordered by SHA-256("601:" + source_id), first half tuning, the rest test. No model
outcome or score is used. See docs/sprints/Sprint_4/HellaSwag_Generalization_Protocol.md.
"""

import argparse
import ast
import hashlib
import json
import math
from pathlib import Path
import re
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from cacheshift.replay_gateway import STRONG, WEAK, load_dataset  # noqa: E402

ROUTERBENCH_SHA = "ba4f77f19517610a707c374e99322d7750c30fc4ae7ff5527888595a1e65d36d"
KEYS_REPO = "Rowan/hellaswag"
KEYS_REVISION = "218ec52e09a7e7462a5400043bb9a69a41d06b76"
KEYS_FILE = "data/validation-00000-of-00001.parquet"
KEYS_SHA = "899813071e1e95efafec90f856e1987d2150fa4d020fc005df6962c259f660cd"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def norm(text):
    return " ".join(str(text).split())


def parse_prompt(prompt):
    """(context, {letter: ending}) from RouterBench's HellaSwag prompt."""
    body = prompt.split("\nPrint only a single choice", 1)[0]
    parts = re.split(r"\n([A-D])\) ", body)
    if len(parts) != 9 or len(set(parts[1::2])) != 4:
        raise ValueError("Expected four unambiguous choices")
    return parts[0], dict(zip(parts[1::2], parts[2::2]))


def split(rows):
    groups = sorted({row["group_id"] for row in rows}, key=lambda g: hashlib.sha256(f"601:{g}".encode()).hexdigest())
    tuning = set(groups[:len(groups) // 2])
    return [{**row, "split": "tuning" if row["group_id"] in tuning else "test"} for row in rows], len(tuning), len(groups) - len(tuning)


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--routerbench", type=Path, required=True)
    parser.add_argument("--keys", type=Path, help="The official validation parquet (default: download the pinned file)")
    parser.add_argument("--download-keys", action="store_true")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit("Output must be new")
    if digest(args.routerbench) != ROUTERBENCH_SHA:
        raise SystemExit("Unexpected RouterBench digest; refusing the pickle")
    keys = args.keys
    if keys is None:
        if not args.download_keys:
            raise SystemExit("Give --keys or --download-keys")
        from huggingface_hub import hf_hub_download
        keys = Path(hf_hub_download(KEYS_REPO, KEYS_FILE, repo_type="dataset", revision=KEYS_REVISION,
                                    cache_dir="data/raw/hf"))
    if digest(keys) != KEYS_SHA:
        raise SystemExit("Unexpected HellaSwag key digest")
    import pandas as pd

    official = pd.read_parquet(keys)
    frame = pd.read_pickle(args.routerbench)
    rows, skipped = [], []
    for _, source in frame.loc[frame.eval_name == "hellaswag"].iterrows():
        qid = str(source.sample_id)
        try:
            item = official.iloc[int(qid.rsplit(".", 1)[1])]
            prompt = ast.literal_eval(source.prompt)
            if len(prompt) != 1:
                raise ValueError("Multi-turn prompt")
            context, choices = parse_prompt(prompt[0])
            if norm(context) != norm(item["ctx"]):
                raise ValueError("Context does not match the official item")
            endings = [norm(e) for e in item["endings"]]
            if sorted(map(norm, choices.values())) != sorted(endings):
                raise ValueError("Endings do not match the official item")
            correct = endings[int(item["label"])]
            letters = [letter for letter, text in choices.items() if norm(text) == correct]
            if len(letters) != 1:
                raise ValueError("Ambiguous correct ending")
            answers = {}
            for model in (STRONG, WEAK):
                answer = ast.literal_eval(source[f"{model}|model_response"])
                cost = float(source[f"{model}|total_cost"])
                if len(answer) != 1 or not isinstance(answer[0], str) or not answer[0].strip() \
                        or not math.isfinite(cost) or cost < 0:
                    raise ValueError("Invalid recorded response/cost")
                answers[model] = {"answer": answer[0], "cost_usd": cost}
            rows.append({"question_id": qid, "group_id": str(item["source_id"]), "activity": str(item["activity_label"]),
                         "text": prompt[0], "is_original": True, "gold_answer": letters[0], "source": "hellaswag",
                         "answers": answers})
        except (ValueError, SyntaxError, TypeError, IndexError) as exc:
            skipped.append({"question_id": qid, "reason": str(exc)})
    rows, tuning_groups, test_groups = split(rows)
    rows.sort(key=lambda row: row["question_id"])
    args.output.mkdir(parents=True)
    dataset = args.output / "questions.jsonl"
    dataset.write_bytes("".join(json.dumps(row) + "\n" for row in rows).encode())
    load_dataset(dataset)
    manifest = {"routerbench_sha256": ROUTERBENCH_SHA, "keys_repo": KEYS_REPO, "keys_revision": KEYS_REVISION,
                "keys_sha256": KEYS_SHA, "dataset_sha256": digest(dataset), "rows": len(rows),
                "tuning": sum(r["split"] == "tuning" for r in rows), "test": sum(r["split"] == "test" for r in rows),
                "groups": {"tuning": tuning_groups, "test": test_groups}, "skipped": skipped,
                "selection": "every aligned RouterBench HellaSwag row; groups = source_id ordered by SHA256(601:source_id), "
                             "first half tuning, rest test; no outcome or score based selection"}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: manifest[k] for k in ("rows", "tuning", "test", "groups", "dataset_sha256")}),
          "skipped:", len(skipped))


if __name__ == "__main__":
    main()
