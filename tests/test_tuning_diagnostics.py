import hashlib
import json

import pytest

from cacheshift.replay_gateway import calibrate_scores
from cacheshift.tuning_diagnostics import diagnose, tuning_points


def test_folds_keep_groups_together_and_fit_without_validation_scores():
    points = [{"question_id": str(i), "group_id": str(i // 2), "score": i / 20} for i in range(20)]
    report = diagnose(points, samples=50)
    assert report == diagnose(points, samples=50)
    for run in report["runs"]:
        seen = []
        for fold in run["folds"]:
            training = set(fold["training_group_ids"])
            validation = set(fold["validation_group_ids"])
            assert not training & validation
            assert training | validation == {point["group_id"] for point in points}
            expected = calibrate_scores([point["score"] for point in points if point["group_id"] in training])
            assert fold["fit"] == expected
            seen.extend(validation)
        assert len(seen) == len(set(seen)) == 10


def test_saved_scores_are_bound_to_tuning_metadata_and_no_answer_labels(tmp_path):
    rows = [{"question_id": f"q{i}", "group_id": f"g{i}", "split": "tuning" if i < 5 else "test"}
            for i in range(6)]  # No question texts or answer labels are required.
    dataset = tmp_path / "data.jsonl"
    dataset.write_text("\n".join(json.dumps(row) for row in rows))
    scores = [0.1, 0.2, 0.3, 0.4, 0.5]
    artifact = {**calibrate_scores(scores), "schema": 1, "cache": "exact", "fit_split": "tuning",
                "dataset_sha256": hashlib.sha256(dataset.read_bytes()).hexdigest(),
                "router_revision": "fixture", "tuning_scores": scores,
                "tuning_miss_ids": [f"q{i}" for i in range(5)]}
    path = tmp_path / "cut.json"
    path.write_text(json.dumps(artifact))
    points, _ = tuning_points(dataset, path)
    assert len(points) == 5 and all(point["question_id"] != "q5" for point in points)
    artifact["tuning_miss_ids"][-1] = "q5"
    path.write_text(json.dumps(artifact))
    with pytest.raises(ValueError, match="non-tuning"):
        tuning_points(dataset, path)


def test_diagnostic_can_report_missed_target_instead_of_forcing_a_pass():
    points = [{"question_id": str(i), "group_id": str(i), "score": 0.5} for i in range(10)]
    report = diagnose(points, samples=20)
    assert all(fold["validation_strong_share"] == 0 for run in report["runs"] for fold in run["folds"])
