from copy import deepcopy
import hashlib
import json
from pathlib import Path

import pytest

from cacheshift.controlled_drift import checks, run, stream
from cacheshift.replay_gateway import calibrate_midgap, calibrate_scores
from cacheshift.retune import load_calibration
from cacheshift.router import REVISION


def test_midgap_preserves_attainable_share_and_opens_boundary():
    scores = [.1, .4, .40000012, .9]
    old = calibrate_scores(scores, .5)
    new = calibrate_midgap(scores, .5)
    assert new["tuning_strong_share"] == old["tuning_strong_share"] == .5
    assert .4 < new["threshold"] < .40000012
    for values in ([.5] * 4, [0., 1.]):
        for target in (0., .5, 1.):
            fit = calibrate_midgap(values, target)
            assert sum(value >= fit["threshold"] for value in values) / len(values) == fit["tuning_strong_share"]


def test_repeat_policy_uses_scores_not_gold_or_recorded_quality():
    rows = {str(i): {"split": "test", "gold_answer": "unused"} for i in range(100)}
    scores = {str(i): i / 100 for i in range(100)}
    high = stream(rows, scores, "test", 601, "high", .5)
    low = stream(rows, scores, "test", 601, "low", .5)
    assert len(high) == 200 and set(high) == set(rows)
    assert sum(scores[qid] >= .5 for qid in high) > sum(scores[qid] >= .5 for qid in low)
    assert high == stream({qid: {"split": "test"} for qid in rows}, scores, "test", 601, "high", .5)


def test_passing_share_without_drift_is_not_a_mechanism_pass():
    stats = {"cache_retuned": {"strong_share_of_routed": {"estimate": .5}, "accuracy": {"estimate": .8}},
             "no_cache": {"accuracy": {"ci95": [.7, .9]}},
             "paired_differences": {"cache_effect": {"strong_share_of_routed": {"estimate": .01, "ci95": [-.01, .03]}}}}
    assert not checks(stats, {"estimate": .01, "ci95": [-.01, .03]})["mechanism_checks_pass"]
    stats["paired_differences"]["retune_effect"] = {"accuracy": {"estimate": -.02, "ci95": [-.03, -.01]}}
    assert checks(stats, {"estimate": .01, "ci95": [-.01, .03]})["paired_accuracy_loss_detected"]


def test_canonical_stage_order_and_artifact_load(tmp_path):
    from test_replay_gateway import records
    sample = records()["q1"]
    rows = {f"{split}{i}": {**deepcopy(sample), "question_id": f"{split}{i}",
                          "group_id": f"{split}{i}", "split": split,
                          "text": f"{split}:{i / 20}", "gold_answer": "B"}
            for split in ("tuning", "test") for i in range(20)}

    class SingleRouter:
        def score(self, text):
            if text.startswith("test:"):
                assert (tmp_path / "run/frozen-fits.json").exists()
            return {"router_score": float(text.split(":")[1])}

        def score_many(self, prompts):
            pytest.fail("Controlled evaluator used batch scoring")

    result = run(rows, SingleRouter(), tmp_path / "run", "digest", samples=50)
    assert len(result["runs"]) == 15
    artifact = load_calibration(tmp_path / "run/calibration.json", "digest", REVISION, rows)
    assert artifact["threshold_rule"] == "midgap" and artifact["scoring_mode"] == "single"
    incompatible = {**artifact, "scoring_mode": "batch"}
    wrong_mode = tmp_path / "wrong-mode.json"
    wrong_mode.write_text(json.dumps(incompatible))
    with pytest.raises(ValueError, match="single scoring"):
        load_calibration(wrong_mode, "digest", REVISION, rows)
    artifact["threshold"] = .1
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(artifact))
    with pytest.raises(ValueError, match="threshold"):
        load_calibration(path, "digest", REVISION, rows)


def test_published_single_calibration_and_complete_audit_provenance():
    from cacheshift.replay_gateway import load_dataset

    root = Path(__file__).parents[1]
    dataset = root / "data/mmlu_retune_20261007/questions.jsonl"
    digest = hashlib.sha256(dataset.read_bytes()).hexdigest()
    records_ = load_dataset(dataset)
    result = root / "experiments/results/controlled-drift-20261012"
    artifact = load_calibration(result / "calibration.json", digest, REVISION, records_)
    assert artifact["scoring_mode"] == "single"
    single = {}
    for split in ("tuning", "test"):
        stage = json.loads((result / f"scores-{split}.json").read_text())
        assert stage["dataset_sha256"] == digest and stage["scoring_mode"] == "single"
        assert set(stage["scores"]) == {qid for qid, row in records_.items() if row["split"] == split}
        single.update(stage["scores"])
    audit = json.loads((result / "batch-single-audit.json").read_text())
    reference = result / audit["paired_score_file"]
    assert hashlib.sha256(reference.read_bytes()).hexdigest() == audit["paired_score_sha256"]
    pairs = [json.loads(line) for line in reference.read_text().splitlines()]
    assert {row["question_id"] for row in pairs} == set(records_)
    assert all(row["single_score"] == single[row["question_id"]] for row in pairs)
    assert max(abs(row["single_score"] - row["batch_score"]) for row in pairs) == audit["max_absolute_score_difference"]
    applied = json.loads((root / "experiments/results/controlled-applied-20261012/report.json").read_text())
    assert applied["calibration_sha256"] == hashlib.sha256((result / "calibration.json").read_bytes()).hexdigest()
