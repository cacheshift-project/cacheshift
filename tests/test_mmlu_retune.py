import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("mmlu_builder", Path(__file__).parents[1] / "tools/build_mmlu_retune.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def rows():
    return [{"question_id": f"{subject}-{i}", "group_id": f"{subject}-stem-{i}",
             "subject": subject, "gold_answer": "A", "answers": {"model": "A"}}
            for subject in ("law", "physics") for i in range(8)]


def test_balanced_split_is_outcome_independent_and_family_disjoint():
    selected, counts = builder.balanced_split(rows(), per_subject=4)
    changed = [{**row, "gold_answer": "D", "answers": {"model": "B"}} for row in reversed(rows())]
    other, _ = builder.balanced_split(changed, per_subject=4)
    assert [(r["question_id"], r["split"]) for r in selected] == [(r["question_id"], r["split"]) for r in other]
    assert all(c["tuning"] == c["test"] == 2 for c in counts.values())
    assert {r["group_id"] for r in selected if r["split"] == "tuning"}.isdisjoint(
        {r["group_id"] for r in selected if r["split"] == "test"})


def test_duplicate_family_has_one_canonical_subject_and_record():
    sample = rows()
    sample.append({**sample[0], "question_id": "duplicate", "subject": "physics"})
    selected, counts = builder.balanced_split(sample, per_subject=8)
    assert len(selected) == len({r["group_id"] for r in selected}) == 16
    assert counts["law"]["eligible_families"] == 8
    assert counts["physics"]["eligible_families"] == 8


def test_insufficient_subject_is_rejected_instead_of_changing_sample():
    with pytest.raises(ValueError, match="Insufficient families"):
        builder.balanced_split(rows()[:-1], per_subject=8)


def test_parser_preserves_choice_order_and_rejects_unknown_format():
    prompt = 'Please answer with the letter of the correct answer.\n\nQuestion\nA) Mars\nB) Earth\nC) Venus\nD) Jupiter\nPrint only a single choice'
    stem, choices = builder.parse_prompt(prompt)
    assert stem == "Question" and choices["B"] == "Earth"
    with pytest.raises(ValueError):
        builder.parse_prompt("different instruction\nA) x\nB) y")
