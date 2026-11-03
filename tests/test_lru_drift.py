import json
import random

import pytest

from cacheshift import lru_drift
from cacheshift.replay_gateway import STRONG, WEAK, ReplayGateway


def synthetic_pool(per_split=40):
    """Tiny pool shaped like the MMLU replay fixture: one question per group."""
    rng = random.Random(7)
    records, scores = {}, {}
    for split in ("tuning", "test"):
        for i in range(per_split):
            qid = f"{split}-{i}"
            score = rng.random()
            gold = "ABCD"[i % 4]
            # The strong model is right more often on high-score questions.
            strong_ok, weak_ok = rng.random() < 0.9, rng.random() < (0.8 - 0.4 * score)
            records[qid] = {"question_id": qid, "group_id": f"g-{qid}", "split": split, "source": "synthetic",
                            "is_original": True, "text": f"Question {qid}?", "gold_answer": gold,
                            "answers": {STRONG: {"answer": gold if strong_ok else "E", "cost_usd": 0.01},
                                        WEAK: {"answer": gold if weak_ok else "E", "cost_usd": 0.001}}}
            scores[qid] = score
    return records, scores


def test_lru_misses_refreshes_hits_and_evicts_least_recent():
    assert lru_drift.lru_misses(list("abacba"), 2) == list("abcba")
    assert lru_drift.lru_misses(list("aaaa"), 1) == ["a"]
    with pytest.raises(ValueError):
        lru_drift.lru_misses(["a"], 0)


def test_lru_misses_match_the_gateway_exactly(tmp_path):
    records, scores = synthetic_pool()
    router = lru_drift.FixedRouter(records, scores)
    test_ids = [qid for qid in records if records[qid]["split"] == "test"]
    stream = random.Random(3).choices(test_ids, k=300)
    gateway = ReplayGateway(records, router, {"threshold": 0.5, "target_strong_share": 0.5},
                            tmp_path / "log.jsonl", cache_capacity=7)
    gateway_misses = [qid for qid in stream if not gateway.answer(qid)["cache_hit"]]
    assert gateway_misses == lru_drift.lru_misses(stream, 7)
    assert len(gateway.cache) == 7


def test_unbounded_gateway_config_is_unchanged(tmp_path):
    records, scores = synthetic_pool(4)
    router = lru_drift.FixedRouter(records, scores)
    calibration = {"threshold": 0.5, "target_strong_share": 0.5}
    plain = ReplayGateway(records, router, calibration, tmp_path / "a.jsonl")
    bounded = ReplayGateway(records, router, calibration, tmp_path / "b.jsonl", cache_capacity=3)
    assert plain.config["cache"] == "exact" and "cache_capacity" not in plain.config
    assert bounded.config["cache"] == "exact-lru" and bounded.config["cache_capacity"] == 3
    assert plain.config_id != bounded.config_id
    with pytest.raises(ValueError):
        ReplayGateway(records, router, calibration, tmp_path / "c.jsonl", cache_capacity=0)


def stats(share, accuracy_low):
    return {"cache_retuned": {"strong_share_of_routed": {"estimate": share}},
            "paired_differences": {"retune_effect": {"accuracy": {"ci95": [accuracy_low, 0.02]}}}}


@pytest.mark.parametrize("share, low, passes", [
    (0.50, -0.005, True),
    (0.53, -0.009, True),      # both on the inside edge
    (0.531, -0.005, False),    # share outside 47-53%
    (0.50, -0.010, False),     # lower bound exactly -1.0 pt is not above it
    (0.50, -0.0175, False),    # the synthetic low-score loss from the controlled study fails
])
def test_pass_rule(share, low, passes):
    assert lru_drift.checks(stats(share, low))["passes"] is passes


def test_small_end_to_end_run_records_protocol_and_decision(tmp_path):
    records, scores = synthetic_pool()
    protocol = tmp_path / "protocol.md"
    protocol.write_text("frozen protocol\n")
    report = lru_drift.run(records, scores, tmp_path / "run", "synthetic-digest", samples=50, seeds=(601,),
                           fractions=(0.25,), arms=(("high", "high"), ("uniform", "low")), protocol=protocol)
    assert report["protocol_file"] == "protocol.md" and len(report["protocol_sha256"]) == 64
    assert [row["arm"] for row in report["runs"]] == ["no_shift", "shift"]
    first = report["runs"][0]
    assert first["capacity"] == 10 and first["tuning_requests"] == 80
    assert first["tuning_misses"] > 40          # a 10-entry LRU cache misses repeats too
    assert 0 < first["test_hit_rate"] < 0.5
    assert [d["arm"] for d in report["decisions"]] == ["no_shift", "shift"]
    assert report["decisions"][0]["seeds"] == [601]
    assert isinstance(report["issue_5_passes"], bool)
    saved = json.loads((tmp_path / "run/report.json").read_text())
    assert saved["accuracy_margin"] == -0.010 and len(saved["runs"]) == 2


def test_pooled_decision_needs_every_seed_share_and_the_pooled_bound(tmp_path):
    records, scores = synthetic_pool()
    router = lru_drift.FixedRouter(records, scores)
    cutoff = lru_drift.calibrate_midgap([scores[q] for q in records if records[q]["split"] == "tuning"], 0.5)["threshold"]
    rows, events = [], {}
    for seed in (601, 602, 603):
        ev, row = lru_drift.run_one(records, router, scores, 10, "uniform", "uniform", seed, cutoff,
                                    tmp_path, "d", samples=50)
        rows.append(row)
        events[seed] = ev
    decision = lru_drift.pooled_decision(rows, events, records, samples=50)
    pooled_requests = sum(len(events[s]["cache_retuned"]) for s in events)
    assert decision["seeds"] == [601, 602, 603] and pooled_requests == 3 * 80
    assert decision["passes"] == (decision["every_seed_share_within_47_53"]
                                  and decision["pooled_accuracy_ci_lower_above_minus_1pt"])
    rows[1]["checks"]["share_within_47_53"] = False  # one seed outside 47-53% fails the decision
    assert lru_drift.pooled_decision(rows, events, records, samples=50)["passes"] is False
