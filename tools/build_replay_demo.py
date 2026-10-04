"""Export 20 development records from the existing keyed ARC prototype fixture."""

import argparse
import hashlib
import json
from pathlib import Path

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("source", type=Path)
parser.add_argument("--output", type=Path, default=Path("data/replay_demo"))
parser.add_argument("--count", type=int, default=20)
parser.add_argument("--tuning-count", type=int, default=10)
args = parser.parse_args()
source = args.source.read_bytes()
expected = "3febcacb162e7da91d024d4171b2feffb4be5a65a2b7f1dae98f67e3472e7b91"
if hashlib.sha256(source).hexdigest() != expected:
    raise ValueError("Expected the verified keyed ARC development fixture")
all_rows = [json.loads(line) for line in source.decode().splitlines()]
if not 0 < args.tuning_count < args.count <= len(all_rows):
    parser.error("Require 0 < tuning-count < count <= source rows")
originals = all_rows[:args.count]
rows = []
group_splits = {}
for index, row in enumerate(originals):
    # For the larger fixture, bind duplicate official ARC IDs to one group.
    group = row["question_id"] if args.count == 20 else "|".join(sorted({ref["arc_id"] for ref in row["reference_sources"]}))
    split = "tuning" if index < args.tuning_count else "test"
    if group in group_splits and group_splits[group] != split:
        raise ValueError("Official ARC question crosses the predeclared split")
    group_splits[group] = split
    rows.append({
        "question_id": row["question_id"], "group_id": group,
        "text": row["prompt"], "is_original": True, "gold_answer": row["reference_answer"],
        "source": row["benchmark"], "split": split,
        "reference_sources": row["reference_sources"],
        "answers": {model: {"answer": result["answer"], "correct": result["recorded_correct"],
                            "cost_usd": result["recorded_cost_usd"]}
                    for model, result in row["results"].items()},
    })
args.output.mkdir(parents=True, exist_ok=False)
payload = ("\n".join(json.dumps(row) for row in rows) + "\n").encode()
(args.output / "questions.jsonl").write_bytes(payload)
manifest = {
    "source_fixture_sha256": expected, "output_sha256": hashlib.sha256(payload).hexdigest(),
    "recorded_answers_source": "https://huggingface.co/datasets/withmartian/routerbench",
    "routerbench_0shot_sha256": "ba4f77f19517610a707c374e99322d7750c30fc4ae7ff5527888595a1e65d36d",
    "answer_keys_source": "https://huggingface.co/datasets/allenai/ai2_arc",
    "key_alignment": "Original fixture joined official keys by question and choice texts, remapping letters to RouterBench choice order",
    "selection": f"First {args.count} rows of existing development fixture, independently of outcomes; first {args.tuning_count} tuning, remaining test",
    "limitations": "Development-only split. Prior exposure and possible router-training overlap preclude research generalization claims. No rewordings or generated model answers.",
}
(args.output / "manifest.json").write_bytes((json.dumps(manifest, indent=2) + "\n").encode())
