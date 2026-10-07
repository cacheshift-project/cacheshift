"""Build an outcome-independent ARC evaluation excluding exposed question families."""

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

from cacheshift.replay_gateway import STRONG, WEAK, load_dataset

SOURCE_SHA = "ba4f77f19517610a707c374e99322d7750c30fc4ae7ff5527888595a1e65d36d"
ARC_SHA = {
    "test": "62f03257e737aed263f55c6abf87c7bb0028a44a6bdd2a26eb1279eb42c1d1e9",
    "train": "e488c1587ffdcfc8443f916c53488a95cd471c5790e0746c6bfe4cecf20962cb",
    "validation": "395a5c88d1580d69855fbaee9450270578df1ad5af6259771cd0a42c20e99f05",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalized(text):
    return " ".join(text.split())


def parse_prompt(prompt):
    parts = re.split(r"\n([A-E])\) ", prompt.split("\nPrint only a single choice", 1)[0])
    if len(parts) < 5 or len(parts) % 2 != 1:
        raise ValueError("Unsupported choice format")
    return parts[0], dict(zip(parts[1::2], parts[2::2]))


def assign_splits(rows):
    """Assign whole stem families using metadata only, independent of row order."""
    groups = sorted({row["group_id"] for row in rows}, key=lambda group: hashlib.sha256(("601:" + group).encode()).hexdigest())
    if len(groups) < 2:
        raise ValueError("At least two question families are required")
    tuning = set(groups[:len(groups) // 2])
    return [{**row, "split": "tuning" if row["group_id"] in tuning else "test"}
            for row in sorted(rows, key=lambda row: row["question_id"])], groups, tuning


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--arc-dir", type=Path, required=True)
    parser.add_argument("--excluded", type=Path, default=Path("data/retune_demo/questions.jsonl"))
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output must be new")
    if digest(args.source) != SOURCE_SHA:
        raise ValueError("Unexpected RouterBench digest; do not unpickle")
    import pandas as pd
    import pyarrow.parquet as pq

    candidates = defaultdict(list)
    arc_files = []
    for split, expected in ARC_SHA.items():
        path = args.arc_dir / f"{split}-00000-of-00001.parquet"
        if digest(path) != expected:
            raise ValueError("Unexpected official ARC digest")
        arc_files.append({"file": path.name, "sha256": expected})
        for row in pq.read_table(path).to_pylist():
            candidates[normalized(row["question"])].append({**row, "split": split})
    exposed = load_dataset(args.excluded)
    excluded_ids = {ref["arc_id"] for row in exposed.values() for ref in row["reference_sources"]}
    excluded_stems = {normalized(parse_prompt(row["text"])[0]) for row in exposed.values()}
    frame = pd.read_pickle(args.source)
    rows, skipped, excluded = [], [], 0
    for _, row in frame.loc[frame.eval_name.eq("arc-challenge")].iterrows():
        qid = str(row.sample_id)
        try:
            prompt_items = ast.literal_eval(row.prompt)
            if len(prompt_items) != 1:
                raise ValueError("Unsupported turns")
            prompt = prompt_items[0]
            stem, choices = parse_prompt(prompt)
            matches = [ref for ref in candidates[normalized(stem)] if
                       Counter(map(normalized, ref["choices"]["text"])) == Counter(map(normalized, choices.values()))]
            if not matches:
                raise ValueError("No official key alignment")
            if normalized(stem) in excluded_stems or any(ref["id"] in excluded_ids for ref in matches):
                excluded += 1
                continue
            keys = set()
            for ref in matches:
                official = dict(zip(ref["choices"]["label"], ref["choices"]["text"]))
                labels = [label for label, text in choices.items() if normalized(text) == normalized(official[ref["answerKey"]])]
                if len(labels) != 1:
                    raise ValueError("Ambiguous key")
                keys.add(labels[0])
            if len(keys) != 1:
                raise ValueError("Conflicting keys")
            answers = {}
            for model in (STRONG, WEAK):
                answer = ast.literal_eval(row[f"{model}|model_response"])
                if len(answer) != 1 or not isinstance(answer[0], str):
                    raise ValueError("Missing recorded response")
                answers[model] = {"answer": answer[0], "cost_usd": float(row[f"{model}|total_cost"])}
            rows.append({"question_id": qid, "group_id": normalized(stem), "text": prompt,
                         "is_original": True, "gold_answer": keys.pop(), "source": "arc-challenge",
                         "reference_sources": [{"arc_id": ref["id"], "split": ref["split"]} for ref in matches],
                         "answers": answers})
        except (ValueError, SyntaxError, TypeError) as error:
            skipped.append({"question_id": qid, "reason": str(error)})
    rows, groups, tuning = assign_splits(rows)
    args.output.mkdir(parents=True)
    data = args.output / "questions.jsonl"
    data.write_text("".join(json.dumps(row) + "\n" for row in rows), encoding="utf-8")
    load_dataset(data)
    manifest = {"routerbench_sha256": SOURCE_SHA, "arc_files": arc_files,
                "excluded_fixture_sha256": digest(args.excluded), "dataset_sha256": digest(data),
                "selection": "All aligned ARC records excluding exposed IDs and normalized question stems; groups ordered by SHA256(601:stem); first half tuning, remaining test. No scores or outcomes used for selection.",
                "rows": len(rows), "groups": len(groups), "tuning_groups": len(tuning),
                "test_groups": len(groups) - len(tuning), "excluded_rows": excluded, "skipped": skipped,
                "limitations": "Fresh relative to our development fixture, not guaranteed independent of router training. Originals and exact repeats only; historical recorded model answers."}
    (args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: manifest[key] for key in ("rows", "groups", "tuning_groups", "test_groups", "excluded_rows", "skipped")}))


if __name__ == "__main__":
    main()
