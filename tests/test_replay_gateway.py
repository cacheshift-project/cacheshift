from copy import deepcopy
import json
import math

from fastapi.testclient import TestClient
import pytest

from cacheshift.gateway import create_app, DATASET
from cacheshift.replay_gateway import STRONG, WEAK, ReplayGateway, calibrate, load_dataset, summarize


class FakeRouter:
    def __init__(self):
        self.calls = []

    def score(self, text):
        self.calls.append(text)
        return {"router_score": {"easy": 0.1, "hard": 0.9, "middle": 0.5}[text]}


def records():
    return {id_: {"question_id": id_, "group_id": id_, "text": text,
                  "is_original": True, "split": split, "source": "test-fixture",
                  "answers": {STRONG: {"answer": "A", "cost_usd": 0.1},
                              WEAK: {"answer": "B", "cost_usd": 0.01}}}
            for id_, text, split in [("t1", "easy", "tuning"), ("t2", "hard", "tuning"),
                                    ("q1", "easy", "test"), ("q2", "hard", "test")]}


def engine(tmp_path, cache=True):
    router = FakeRouter()
    data = records()
    calibration = calibrate(data, router)
    router.calls.clear()
    return ReplayGateway(data, router, calibration, tmp_path / "events.jsonl", cache_enabled=cache)


def test_cache_bypasses_router_preserves_wrong_answers_and_cost(tmp_path):
    gateway = engine(tmp_path)
    first = gateway.answer("q1")
    second = gateway.answer("q1")
    assert first["route"] == "weak" and first["cost_usd"] == 0.01
    assert second["route"] == "cache" and second["cost_usd"] == 0
    assert first["answer"] == second["answer"] == "B"
    assert second["model"] == WEAK and second["router_score"] is None
    assert second["matched_question_id"] == "q1" and second["similarity"] == 1
    assert gateway.router.calls == ["easy"]
    log = [json.loads(line) for line in gateway.log_path.read_text().splitlines()]
    assert log == [first, second]
    assert first["request_id"] != second["request_id"]


def test_http_validation_and_routing(tmp_path):
    gateway = engine(tmp_path)
    with TestClient(create_app(gateway)) as client:
        assert client.get("/health").json()["mode"] == "recorded-answer-replay"
        assert len(client.get("/questions").json()) == 2
        for id_ in ("unknown", "t1"):
            assert client.post("/replay", json={"question_id": id_}).status_code == 404
        assert client.post("/replay", json={"question_id": "q1", "text": "new text"}).status_code == 422
        assert client.post("/replay", json={"question_id": 4}).status_code == 422
        assert client.post("/replay", json={}).status_code == 422
        assert not gateway.router.calls
        response = client.post("/replay", json={"question_id": "q2"})
        assert response.status_code == 200
        assert response.json()["model"] == STRONG
        assert response.json()["router_score"] == 0.9


def test_uncached_repeats_really_route_and_summary_denominators(tmp_path):
    gateway = engine(tmp_path, cache=False)
    events = [gateway.answer(id_) for id_ in ("q1", "q2", "q2")]
    assert len(gateway.router.calls) == 3
    assert summarize(events, 0.5)["strong_share_of_routed"] == pytest.approx(2/3)
    cached = engine(tmp_path / "cached")
    events = [cached.answer(id_) for id_ in ("q1", "q2", "q2")]
    summary = summarize(events, 0.5)
    assert summary["strong_share_of_routed"] == 0.5
    assert summary["strong_share_of_all"] == pytest.approx(1/3)
    assert summary["historical_model_cost_usd"] == pytest.approx(0.11)
    assert summarize([], 0.5)["strong_share_of_routed"] is None


def test_calibration_reads_tuning_prompts_only_and_handles_ties():
    router = FakeRouter()
    data = records()
    data["t1"]["answers"] = None  # outcomes must never be needed for calibration
    data["t2"]["answers"] = None
    data["q1"]["text"] = "never score test prompts during tuning"
    result = calibrate(data, router)
    assert router.calls == ["easy", "hard"]
    assert result["tuning_strong_share"] == 0.5
    data["t2"]["text"] = "easy"
    assert calibrate(data, router)["tuning_strong_share"] == 0.0
    assert calibrate(data, router, 0)["tuning_strong_share"] == 0
    assert calibrate(data, router, 1)["tuning_strong_share"] == 1
    with pytest.raises(ValueError):
        calibrate(data, router, math.nan)


@pytest.mark.parametrize("mutation", ["cost", "group", "duplicate", "rewording", "missing_model"])
def test_invalid_datasets_rejected(tmp_path, mutation):
    rows = list(deepcopy(records()).values())
    if mutation == "cost":
        rows[0]["answers"][WEAK]["cost_usd"] = -1
    elif mutation == "group":
        rows[2]["group_id"] = rows[0]["group_id"]
    elif mutation == "duplicate":
        rows.append(rows[0])
    elif mutation == "rewording":
        rows[2]["is_original"] = False
    else:
        del rows[0]["answers"][WEAK]
    path = tmp_path / "data.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows))
    with pytest.raises(ValueError):
        load_dataset(path)


def test_demo_fixture_provenance_and_split():
    import hashlib
    data = load_dataset(DATASET)
    assert len(data) == 20
    assert sum(row["split"] == "tuning" for row in data.values()) == 10
    manifest = json.loads(DATASET.with_name("manifest.json").read_text())
    assert hashlib.sha256(DATASET.read_bytes()).hexdigest() == manifest["output_sha256"]


def test_existing_logs_are_not_overwritten(tmp_path):
    gateway = engine(tmp_path)
    gateway.answer("q1")
    before = gateway.log_path.read_bytes()
    with pytest.raises(FileExistsError):
        engine(tmp_path)
    assert before == gateway.log_path.read_bytes()
