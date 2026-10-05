from copy import deepcopy
import json

import pytest

from cacheshift.retune import acceptance, fit, is_correct, load_calibration, paired_report, question_stream, run
from cacheshift.replay_gateway import ReplayGateway


class NumericRouter:
    def __init__(self):
        self.calls = []

    def score(self, text):
        self.calls.append(text)
        return {"router_score": float(text)}


def data():
    from test_replay_gateway import records
    sample = records()["q1"]
    return {f"{split}{i}": {**deepcopy(sample), "question_id": f"{split}{i}",
                            "group_id": f"{split}{i}", "text": str(score),
                            "gold_answer": "B", "split": split}
            for split in ("tuning", "test") for i, score in enumerate((0.1, 0.4, 0.6, 0.9))}


def test_fit_removes_repeats_and_never_reads_labels_or_test():
    records = data()
    for row in records.values():
        row.pop("answers")
        row.pop("gold_answer")
        if row["split"] == "test":
            row["text"] = "must not be scored"
    stream = ["tuning0", "tuning1", "tuning2"] + ["tuning3"] * 5
    router = NumericRouter()
    base = fit(records, router, stream, 0.5, False)
    router.calls.clear()
    fixed = fit(records, router, stream, 0.5, True)
    assert base["threshold"] == 0.9 and fixed["threshold"] == 0.6
    assert fixed["tuning_strong_share"] == 0.5
    assert router.calls == ["0.1", "0.4", "0.6", "0.9"]
    with pytest.raises(ValueError, match="tuning IDs"):
        fit(records, router, ["test0"], 0.5, True)


def test_paired_evaluation_clusters_repeated_questions_and_acceptance(tmp_path):
    records, router = data(), NumericRouter()
    tuning = ["tuning0", "tuning1", "tuning2"] + ["tuning3"] * 5
    base, fixed = [fit(records, router, tuning, 0.5, cache) for cache in (False, True)]
    events = {}
    for name, cut, cache in (("no_cache", base, False), ("cache_untuned", base, True),
                              ("cache_retuned", fixed, True)):
        gateway = ReplayGateway(records, router, cut, tmp_path / f"{name}.jsonl", cache_enabled=cache)
        events[name] = [gateway.answer(qid) for qid in ["test0", "test1", "test2"] + ["test3"] * 5]
    report = paired_report(events, records, 601, samples=300)
    assert report["cache_untuned"]["strong_share_of_routed"]["estimate"] == 0.25
    assert report["cache_retuned"]["strong_share_of_routed"]["estimate"] == 0.5
    assert report["cache_retuned"]["accuracy"]["estimate"] == 0.25
    assert acceptance(report, 0.5)["share_within_3_percentage_points"]
    assert not acceptance(report, 0.8)["share_within_3_percentage_points"]
    assert paired_report(events, records, 601, samples=300) == report
    # Identical traces must have zero paired differences, even with wide marginal CIs.
    identical = {name: events["no_cache"] for name in events}
    delta = paired_report(identical, records, 601, samples=300)["paired_differences"]["cache_effect"]
    assert all(value["ci95"] == [0.0, 0.0] for value in delta.values())


def test_artifact_binding_and_threshold_tampering(tmp_path):
    result = fit(data(), NumericRouter(), ["tuning0", "tuning1", "tuning2", "tuning3"], 0.5, True)
    artifact = {**result, "schema": 1, "fit_split": "tuning", "dataset_sha256": "data", "router_revision": "router"}
    path = tmp_path / "cut.json"
    path.write_text(json.dumps(artifact))
    assert load_calibration(path, "data", "router")["threshold"] == 0.6
    invalid = data()
    invalid["tuning0"]["split"] = "test"
    with pytest.raises(ValueError, match="non-tuning"):
        load_calibration(path, "data", "router", invalid)
    with pytest.raises(ValueError):
        load_calibration(path, "different-data", "router")
    artifact["threshold"] = 0.9
    path.write_text(json.dumps(artifact))
    with pytest.raises(ValueError, match="threshold"):
        load_calibration(path, "data", "router")


def test_stream_split_and_official_label_parser():
    stream = question_stream(data(), "test", 601)
    assert len(stream) == 8 and all(qid.startswith("test") for qid in stream)
    assert question_stream(data(), "test", 601) == stream
    assert is_correct({"gold_answer": "B"}, "B)")
    assert not is_correct({"gold_answer": "B"}, "B or C")
    with pytest.raises(ValueError):
        is_correct({}, "B")


def test_five_seed_command_pipeline_preserves_evidence_and_never_overwrites(tmp_path):
    import hashlib
    from cacheshift.router import REVISION
    output = tmp_path / "new-run"
    records = data()
    report = run(records, NumericRouter(), output, "data", samples=50)
    assert len(report["runs"]) == 5
    assert json.loads((output / "report.json").read_text()) == report
    for seed in report["runs"]:
        for name, digest in seed["trace_sha256"].items():
            path = output / "raw" / f"{seed['seed']}-{name}.jsonl"
            assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
        calibration = load_calibration(output / f"calibration-{seed['seed']}.json", "data", REVISION, records)
        assert calibration["threshold"] == 0.6
    with pytest.raises(FileExistsError):
        run(records, NumericRouter(), output, "data", samples=50)
