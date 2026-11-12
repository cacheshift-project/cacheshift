import json

import numpy as np
import pytest

from cacheshift import semantic_gateway_check
from cacheshift.replay_gateway import STRONG, WEAK, ReplayGateway, calibrate


class FakeRouter:
    def __init__(self):
        self.calls = []

    def score(self, text):
        self.calls.append(text)
        return {"router_score": 0.9 if "hard" in text else 0.1}


class FakeEmbedder:
    """Unit vectors with known similarities: Sunday is 0.94 from Saturday, bread 0.75 from cookies."""

    model_name = "fake-embedder"
    near = {"close on Sunday": ("close on Saturday", 0.94), "gluten-free bread": ("gluten-free cookies", 0.75)}

    def __init__(self):
        self.vectors = {}

    def __call__(self, text):
        if text not in self.vectors:
            other = np.zeros(32, dtype=np.float32)
            other[len(self.vectors) + 1] = 1.0
            if text in self.near:
                target, cos = self.near[text]
                other = (cos * self(target) + np.sqrt(1 - cos**2) * other).astype(np.float32)
            self.vectors[text] = other
        return self.vectors[text]


def records():
    rows = {}
    for id_, text, split, gold in [("t1", "easy tuning", "tuning", "A"), ("t2", "hard tuning", "tuning", "A"),
                                   ("sat", "close on Saturday", "test", "A"), ("sun", "close on Sunday", "test", "B"),
                                   ("cookies", "gluten-free cookies", "test", "C"),
                                   ("bread", "gluten-free bread", "test", "D")]:
        rows[id_] = {"question_id": id_, "group_id": id_, "text": text, "is_original": True, "split": split,
                     "source": "test-fixture", "gold_answer": gold,
                     "answers": {STRONG: {"answer": gold, "cost_usd": 0.1}, WEAK: {"answer": "E", "cost_usd": 0.01}}}
    return rows


def engine(tmp_path, threshold=0.90, **kwargs):
    router, data = FakeRouter(), records()
    calibration = calibrate(data, router)
    router.calls.clear()
    return ReplayGateway(data, router, calibration, tmp_path / "events.jsonl",
                         semantic_threshold=threshold, embed=FakeEmbedder(), **kwargs)


def test_semantic_hit_on_a_different_question_is_logged_with_its_match(tmp_path):
    gateway = engine(tmp_path)
    first = gateway.answer("sat")
    second = gateway.answer("sun")
    assert not first["cache_hit"] and first["matched_question_id"] is None and first["similarity"] is None
    assert second["cache_hit"] and second["route"] == "cache" and second["cost_usd"] == 0
    assert second["matched_question_id"] == "sat" and second["similarity"] == pytest.approx(0.94, abs=1e-6)
    assert second["answer"] == first["answer"]  # Saturday's answer served to the Sunday question
    assert gateway.router.calls == ["close on Saturday"]
    assert [json.loads(line) for line in gateway.log_path.read_text().splitlines()] == [first, second]


def test_below_the_setting_is_a_miss_and_only_misses_are_saved(tmp_path):
    gateway = engine(tmp_path)
    gateway.answer("cookies")
    bread = gateway.answer("bread")  # 0.75 < 0.90: routed and saved
    assert not bread["cache_hit"] and gateway.router.calls == ["gluten-free cookies", "gluten-free bread"]
    again = gateway.answer("bread")
    assert again["cache_hit"] and again["matched_question_id"] == "bread"
    gateway.answer("sat")
    gateway.answer("sun")  # hit on Saturday's entry, so Sunday is never saved itself
    assert gateway.answer("sun")["matched_question_id"] == "sat"
    assert len(gateway.semantic.entries) == 3


def test_looser_setting_matches_more(tmp_path):
    gateway = engine(tmp_path, threshold=0.70)
    gateway.answer("cookies")
    assert gateway.answer("bread")["matched_question_id"] == "cookies"


def test_config_records_the_semantic_setting_and_exact_runs_are_unchanged(tmp_path):
    gateway = engine(tmp_path)
    assert gateway.config["cache"] == "semantic" and gateway.config["semantic_threshold"] == 0.90
    assert gateway.config["embedding_model"] == "fake-embedder"
    router, data = FakeRouter(), records()
    exact = ReplayGateway(data, router, calibrate(data, router), tmp_path / "exact.jsonl")
    assert exact.semantic is None and "semantic_threshold" not in exact.config
    assert exact.config_id != gateway.config_id


@pytest.mark.parametrize("kwargs", [{"cache_enabled": False}, {"cache_capacity": 10}, {"threshold": 1.5}])
def test_invalid_semantic_settings_rejected(tmp_path, kwargs):
    with pytest.raises(ValueError):
        engine(tmp_path, **kwargs)


def test_semantic_setting_needs_an_embedder(tmp_path):
    router, data = FakeRouter(), records()
    with pytest.raises(ValueError, match="embed"):
        ReplayGateway(data, router, calibrate(data, router), tmp_path / "e.jsonl", semantic_threshold=0.9)


def test_cross_check_matches_story2_replay_request_by_request(tmp_path):
    data, router, embed = records(), FakeRouter(), FakeEmbedder()
    stream = ["sat", "sun", "cookies", "bread", "bread", "sun", "sat"]
    result = semantic_gateway_check.check(data, stream, router, calibrate(data, router), embed, tmp_path, "digest",
                                          thresholds=(0.90, 0.70))
    assert result["passes"]
    tight, loose = result["settings"]["cos>=0.90"], result["settings"]["cos>=0.70"]
    assert (tight["hits"], tight["wrong_question_hits"], tight["mismatches"]) == (4, 2, 0)
    assert (loose["hits"], loose["wrong_question_hits"], loose["mismatches"]) == (5, 4, 0)
    assert tight["story2_offline_wrong_question_hits"] == 2


def test_compare_reports_a_different_match():
    gateway = [{"question_id": "sun", "cache_hit": True, "matched_question_id": "sat"}]
    story2 = [{"question_id": "sun", "cache_hit": True, "matched_question_id": "sun"}]
    [mismatch] = semantic_gateway_check.compare(gateway, story2)
    assert mismatch["gateway"] == [True, "sat"] and mismatch["story2"] == [True, "sun"]
    assert semantic_gateway_check.compare(gateway, gateway) == []
