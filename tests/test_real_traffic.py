import json
import random

import numpy as np
import pytest

from cacheshift import real_traffic
from cacheshift.replay_gateway import calibrate_midgap


class FakeRouter:
    """Scores from a fixed table; counts calls so resume can be checked."""

    def __init__(self, scores):
        self.scores, self.calls = scores, 0

    def score_many(self, prompts, batch_size=4):
        assert batch_size == 1 and len(prompts) == 1
        self.calls += 1
        return [{"router_score": self.scores[prompts[0]], "input_tokens": 10, "truncated": False}]


def synthetic_groups(n_repeated=60, n_one_off=400, repeated_score=0.3, seed=5):
    """Repeated keys score low (easy), one-off keys score uniformly."""
    rng = random.Random(seed)
    groups, scores = {}, {}
    for i in range(n_repeated):
        key = f"repeated {i}"
        groups[key], scores[key] = rng.randint(2, 6), min(1.0, max(0.0, rng.gauss(repeated_score, 0.05)))
    for i in range(n_one_off):
        key = f"one-off {i}"
        groups[key], scores[key] = 1, rng.random()
    return groups, scores


def test_normalize_trims_and_collapses_whitespace_but_keeps_case():
    assert real_traffic.normalize("  What  is\n\tAI? ") == "What is AI?"
    assert real_traffic.normalize("What is AI?") != real_traffic.normalize("what is ai?")
    assert real_traffic.normalize(None) == "" and real_traffic.normalize("   ") == ""


def test_first_user_message_skips_other_roles():
    conversation = [{"role": "system", "content": "be nice"}, {"role": "user", "content": "hi"},
                    {"role": "user", "content": "later"}]
    assert real_traffic.first_user_message(conversation) == "hi"
    assert real_traffic.first_user_message([{"role": "assistant", "content": "x"}]) is None


ALL = {"multi": 1.0, "pair": 1.0, "one_off": 1.0}  # every key scored


def test_sample_keys_scores_all_large_groups_and_samples_the_rest():
    groups = {f"m{i}": 3 + i for i in range(10)} | {f"p{i}": 2 for i in range(50)} | {f"o{i}": 1 for i in range(100)}
    first = real_traffic.sample_keys(groups, seed=601, one_off_sample=30, pair_sample=20)
    assert first == real_traffic.sample_keys(groups, seed=601, one_off_sample=30, pair_sample=20)
    sampled, weights = first
    assert len(sampled["multi"]) == 10 and weights["multi"] == 1
    assert len(sampled["pair"]) == 20 and all(groups[k] == 2 for k in sampled["pair"]) and weights["pair"] == 2.5
    assert len(sampled["one_off"]) == 30 and all(groups[k] == 1 for k in sampled["one_off"])
    sampled, weights = real_traffic.sample_keys(groups, one_off_sample=500, pair_sample=500)
    assert len(sampled["pair"]) == 50 and len(sampled["one_off"]) == 100 and weights == ALL


def test_weighted_midgap_matches_calibrate_midgap_with_unit_weights():
    rng = random.Random(3)
    for n in (5, 40, 301):
        scores = [round(rng.random(), 3) for _ in range(n)]
        assert real_traffic.weighted_midgap(scores, np.ones(n))["threshold"] == \
            pytest.approx(calibrate_midgap(scores, 0.5)["threshold"])


def test_weighted_midgap_uses_weights():
    # Two prompts; the low-score one is asked nine times, so 50% of requests cannot be met exactly.
    result = real_traffic.weighted_midgap([0.2, 0.8], [9, 1])
    assert result["strong_share_of_requests"] == pytest.approx(0.1)


def test_score_keys_writes_no_text_and_resumes(tmp_path):
    scores = {"alpha prompt": 0.4, "beta prompt": 0.7}
    router = FakeRouter(scores)
    raw = tmp_path / "raw" / "scores.jsonl"
    first = real_traffic.score_keys(["alpha prompt"], router, raw)
    assert first["alpha prompt"]["router_score"] == 0.4 and router.calls == 1
    both = real_traffic.score_keys(["alpha prompt", "beta prompt"], router, raw)
    assert router.calls == 2 and both["beta prompt"]["router_score"] == 0.7
    text = raw.read_text(encoding="utf-8")
    assert "alpha" not in text and "beta" not in text


def test_easy_repeats_push_the_share_up_and_are_detected():
    groups, scores = synthetic_groups()
    scored = {key: {"router_score": scores[key], "truncated": False} for key in groups}
    result = real_traffic.analyze(groups, scored, ALL, samples=200)
    est, ci = result["estimates"], result["intervals_95"]
    # Easy prompts are absorbed by the cache, so the router sees a harder mix.
    assert est["cache_off_share"] == pytest.approx(0.5, abs=0.05)
    assert est["unbounded_drift"] > 0.05 and ci["unbounded_drift"][0] > 0.05
    assert est["score_gap"] < 0 and ci["score_gap"][1] < 0
    assert result["decision"].startswith("drift matters")


def test_no_skew_gives_no_drift():
    groups, _ = synthetic_groups(n_repeated=200)
    rng = random.Random(9)
    scores = {key: rng.random() for key in groups}  # same distribution in both strata
    scored = {key: {"router_score": scores[key], "truncated": False} for key in groups}
    result = real_traffic.analyze(groups, scored, ALL, samples=200)
    low, high = result["intervals_95"]["unbounded_drift"]
    assert low < 0 < high


def test_a_weighted_sample_estimates_the_full_population():
    groups, scores = synthetic_groups(n_repeated=400, n_one_off=4000)
    everything = {key: {"router_score": scores[key], "truncated": False} for key in groups}
    full = real_traffic.analyze(groups, everything, ALL, samples=20)["estimates"]
    sampled, weights = real_traffic.sample_keys(groups, one_off_sample=1500, pair_sample=60)
    subset = {key: everything[key] for keys in sampled.values() for key in keys}
    part = real_traffic.analyze(groups, subset, weights, samples=20)
    assert part["estimated_keys"]["one_off"] == pytest.approx(4000)
    assert part["estimates"]["unbounded_drift"] == pytest.approx(full["unbounded_drift"], abs=0.03)
    assert part["estimates"]["score_gap"] == pytest.approx(full["score_gap"], abs=0.03)


def test_sensitivity_checks_run_and_pairs_count_once():
    groups, scores = synthetic_groups()
    groups["NAME_1 says hi"], scores["NAME_1 says hi"] = 150, 0.01
    scored = {key: {"router_score": scores[key], "truncated": False} for key in groups}
    checks = real_traffic.sensitivity(groups, scored, ALL, samples=20)
    assert set(checks) == set(real_traffic.SENSITIVITY_LABELS)
    main = real_traffic.analyze(groups, scored, ALL, samples=20)
    assert checks["pairs_as_one_request"]["estimated_keys"]["one_off"] > main["estimated_keys"]["one_off"]
    assert sum(checks["without_name_tags"]["scored_keys"].values()) == len(groups) - 1
    assert sum(checks["without_automated"]["scored_keys"].values()) == len(groups) - 1


def test_lru_drift_with_a_huge_cache_equals_the_unbounded_drift():
    groups, scores = synthetic_groups()
    keys = [key for key, count in groups.items() for _ in range(count)]
    misses = real_traffic.lru_miss_counts(keys, len(groups), fractions=(1.0,), seeds=(601,))
    scored = {key: {"router_score": scores[key], "truncated": False} for key in groups}
    result = real_traffic.analyze(groups, scored, ALL, misses_by_order=misses, samples=50)
    assert result["lru"][0]["drift"] == pytest.approx(result["estimates"]["unbounded_drift"])


@pytest.mark.parametrize("interval,expected", [
    ((0.06, 0.09), "drift matters"), ((-0.09, -0.06), "drift matters"),
    ((-0.02, 0.03), "drift too small"), ((0.01, 0.07), "inconclusive")])
def test_decision_rule(interval, expected):
    assert real_traffic.decide(interval).startswith(expected)


def test_markdown_contains_numbers_only(tmp_path):
    groups, scores = synthetic_groups()
    keys = [key for key, count in groups.items() for _ in range(count)]
    scored = {key: {"router_score": scores[key], "truncated": False} for key in groups}
    misses = real_traffic.lru_miss_counts(keys, len(groups), fractions=(0.1,), seeds=(601,))
    report = {"plan_file": "Real_Traffic_Plan.md", "plan_sha256": "0" * 64, "capacity_fractions": [0.1],
              "traffic": {"conversations": 1000, "requests": len(keys), "non_english_share": 0.2,
                          "unique_keys": len(groups), "repeated_groups": 60, "repeat_rate": 0.3},
              "main": real_traffic.analyze(groups, scored, ALL, misses_by_order=misses, samples=50),
              "sensitivity": real_traffic.sensitivity(groups, scored, ALL, samples=20)}
    text = real_traffic.markdown(report)
    assert "repeated 1" not in text and "one-off 1" not in text
    json.dumps(report)  # report must be JSON-serializable
