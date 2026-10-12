"""Build a subject-balanced, outcome-independent MMLU calibration/test fixture."""

import argparse
import ast
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

from cacheshift.replay_gateway import STRONG, WEAK, load_dataset

ROUTERBENCH_SHA = "ba4f77f19517610a707c374e99322d7750c30fc4ae7ff5527888595a1e65d36d"
MMLU_REVISION = "c30699e8356da336a370243923dbaf21066bb9fe"
MMLU_SHA = "74a41822ce7d3def56e1682f958469c04642a5336a5ce912fa375fdb90fb25d7"
MMLU_URL = f"https://huggingface.co/datasets/cais/mmlu/resolve/{MMLU_REVISION}/all/test-00000-of-00001.parquet"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def normalize(text):
    return " ".join(text.split())


def parse_prompt(prompt):
    prefix = "Please answer with the letter of the correct answer.\n\n"
    if not prompt.startswith(prefix):
        raise ValueError("Unknown MMLU instruction")
    body = prompt[len(prefix):].split("\nPrint only a single choice", 1)[0]
    parts = re.split(r"\n([A-D])\) ", body)
    if len(parts) != 9 or len(set(parts[1::2])) != 4:
        raise ValueError("Expected four unambiguous choices")
    return parts[0], dict(zip(parts[1::2], parts[2::2]))


def balanced_split(rows, per_subject=64):
    """Select whole families using subject and stem only, not model outcomes."""
    if per_subject < 4 or per_subject % 2:
        raise ValueError("Use an even sample of at least four per subject")
    by_subject = defaultdict(dict)
    seen = set()
    # If a stem occurs in more than one subject, retain one canonical subject.
    for row in sorted(rows, key=lambda r: (r["subject"], r["question_id"])):
        if row["group_id"] in seen:
            continue
        seen.add(row["group_id"])
        by_subject[row["subject"]][row["group_id"]] = row
    selected, counts = [], {}
    for subject, families in sorted(by_subject.items()):
        if len(families) < per_subject:
            raise ValueError(f"Insufficient families in {subject}: {len(families)}")
        groups = sorted(families, key=lambda group: hashlib.sha256(("601:" + group).encode()).hexdigest())[:per_subject]
        # Selection and split are both fixed independently of scores/answers.
        for i, group in enumerate(groups):
            selected.append({**families[group], "split": "tuning" if i < per_subject // 2 else "test"})
        counts[subject] = {"eligible_families": len(families), "tuning": per_subject // 2, "test": per_subject // 2}
    if not selected:
        raise ValueError("No aligned MMLU families")
    return sorted(selected, key=lambda row: row["question_id"]), counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--routerbench", type=Path, required=True)
    parser.add_argument("--keys", type=Path, default=Path("data/raw/mmlu-test.parquet"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--download-keys", action="store_true")
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError("Output must be new")
    if digest(args.routerbench) != ROUTERBENCH_SHA:
        raise ValueError("Unexpected RouterBench digest; refusing pickle")
    if args.download_keys and not args.keys.exists():
        import ssl
        from urllib.request import urlopen
        import certifi

        with urlopen(MMLU_URL, timeout=120,
                     context=ssl.create_default_context(cafile=certifi.where())) as response:
            content = response.read()
        if hashlib.sha256(content).hexdigest() != MMLU_SHA:
            raise ValueError("Unexpected downloaded key digest")
        args.keys.parent.mkdir(parents=True, exist_ok=True)
        args.keys.write_bytes(content)
    if digest(args.keys) != MMLU_SHA:
        raise ValueError("Unexpected MMLU key digest")
    import pandas as pd
    import pyarrow.parquet as pq

    index = defaultdict(list)
    for row in pq.read_table(args.keys).to_pylist():
        index[(row["subject"], normalize(row["question"]))].append(row)
    frame = pd.read_pickle(args.routerbench)
    aligned, skipped = [], []
    for _, source in frame.loc[frame.eval_name.str.startswith("mmlu-")].iterrows():
        qid = str(source.sample_id)
        subject = source.eval_name[len("mmlu-"):].replace("-", "_")
        try:
            prompt = ast.literal_eval(source.prompt)
            if len(prompt) != 1:
                raise ValueError("Multi-turn prompt")
            stem, choices = parse_prompt(prompt[0])
            matches = [row for row in index[(subject, normalize(stem))] if
                       Counter(map(normalize, row["choices"])) == Counter(map(normalize, choices.values()))]
            if not matches:
                raise ValueError("No official stem-and-choices match")
            labels = set()
            for row in matches:
                correct = row["choices"][int(row["answer"])]
                remapped = [label for label, text in choices.items() if normalize(text) == normalize(correct)]
                if len(remapped) != 1:
                    raise ValueError("Ambiguous correct choice")
                labels.add(remapped[0])
            if len(labels) != 1:
                raise ValueError("Conflicting official keys")
            answers = {}
            for model in (STRONG, WEAK):
                answer = ast.literal_eval(source[f"{model}|model_response"])
                cost = float(source[f"{model}|total_cost"])
                if len(answer) != 1 or not isinstance(answer[0], str) or not answer[0].strip() or not math.isfinite(cost) or cost < 0:
                    raise ValueError("Invalid recorded response/cost")
                answers[model] = {"answer": answer[0], "cost_usd": cost}
            aligned.append({"question_id": qid, "group_id": normalize(stem), "subject": subject,
                            "text": prompt[0], "is_original": True, "gold_answer": labels.pop(),
                            "source": "mmlu", "answers": answers})
        except (ValueError, SyntaxError, TypeError) as exc:
            skipped.append({"question_id": qid, "reason": str(exc)})
    rows, counts = balanced_split(aligned)
    args.output.mkdir(parents=True)
    dataset = args.output / "questions.jsonl"
    dataset.write_bytes("".join(json.dumps(row) + "\n" for row in rows).encode())
    load_dataset(dataset)
    manifest = {"routerbench_sha256": ROUTERBENCH_SHA, "keys_sha256": MMLU_SHA,
                "keys_revision": MMLU_REVISION, "keys_url": MMLU_URL,
                "dataset_sha256": digest(dataset), "per_subject": counts, "rows": len(rows),
                "skipped": skipped, "selection": "64 canonical stem families per subject ordered by SHA256(601:stem), first 32 tuning, remaining 32 test; no outcome or score based selection",
                "limitations": "New relative to local ARC evaluations, but possible benchmark overlap in released router training. Subject-balanced synthetic traffic, exact repeats and historical recorded responses only."}
    (args.output / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())
    print(json.dumps({"rows": len(rows), "subjects": len(counts), "aligned": len(aligned), "skipped": len(skipped), "dataset_sha256": manifest["dataset_sha256"]}))


if __name__ == "__main__":
    main()
