import importlib.util
import hashlib
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("holdout_builder", Path(__file__).parents[1] / "tools/build_retune_holdout.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def test_family_split_ignores_answers_costs_and_input_order():
    rows = [{"question_id": str(i), "group_id": group, "answers": {"model": "A"}}
            for i, group in enumerate(["stem one", "stem two", "stem one", "stem three", "stem four"])]
    assigned, _, tuning = builder.assign_splits(rows)
    changed = [{**row, "answers": {"model": "wrong"}, "gold_answer": "E", "cost_usd": 999}
               for row in reversed(rows)]
    other, _, _ = builder.assign_splits(changed)
    assert [(row["question_id"], row["split"]) for row in assigned] == [(row["question_id"], row["split"]) for row in other]
    assert len(tuning) == 2
    assert assigned[0]["split"] == assigned[2]["split"]


def test_insufficient_families_rejected():
    with pytest.raises(ValueError, match="two question families"):
        builder.assign_splits([{"question_id": "a", "group_id": "same"}])


def test_choice_order_does_not_change_normalized_stem():
    left, _ = builder.parse_prompt("Which planet?\nA) Earth\nB) Mars\nPrint only a single choice")
    right, _ = builder.parse_prompt("Which   planet?\nA) Mars\nB) Earth\nPrint only a single choice")
    assert builder.normalized(left) == builder.normalized(right)


def test_committed_holdout_and_calibration_share_canonical_digest():
    from cacheshift.retune import load_calibration
    from cacheshift.router import REVISION

    root = Path(__file__).parents[1]
    dataset = root / "data/retune_holdout_20261007/questions.jsonl"
    assert b"\r\n" not in dataset.read_bytes()
    checksum = hashlib.sha256(dataset.read_bytes()).hexdigest()
    manifest = json.loads(dataset.with_name("manifest.json").read_text())
    assert checksum == manifest["dataset_sha256"]
    records = builder.load_dataset(dataset)
    for seed in range(601, 606):
        load_calibration(root / f"experiments/results/retune-20261007/calibration-{seed}.json",
                         checksum, REVISION, records)
