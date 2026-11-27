import json

from fastapi.testclient import TestClient
import numpy as np
import pytest

from cacheshift import dashboard, report
from cacheshift.cache_quality import request_stream
from cacheshift.replay_gateway import STRONG, WEAK, calibrate


class FakeRouter:
    def score(self, text):
        return {"router_score": 0.9 if "hard" in text or "Sunday" in text else 0.1}


class FakeEmbedder:
    """Sunday is 0.94 alike to Saturday; everything else is unrelated."""

    model_name = "fake-embedder"

    def __init__(self):
        self.vectors = {}

    def __call__(self, text):
        if text not in self.vectors:
            vector = np.zeros(16, dtype=np.float32)
            vector[len(self.vectors) + 1] = 1.0
            if "Sunday" in text:
                vector = (0.94 * self("When do you close on Saturday?\nA) 5pm\nB) 6pm\nAnswer:")
                          + np.sqrt(1 - 0.94**2) * vector).astype(np.float32)
            self.vectors[text] = vector
        return self.vectors[text]


def records():
    rows = {}
    for qid, text, split, gold in [
            ("t1", "easy tuning", "tuning", "A"), ("t2", "hard tuning", "tuning", "A"),
            ("sat", "When do you close on Saturday?\nA) 5pm\nB) 6pm\nAnswer:", "test", "A"),
            ("sun", "When do you close on Sunday?\nA) 5pm\nB) 6pm\nAnswer:", "test", "B"),
            ("bread", "Is the bread vegan?\nA) Yes\nB) No\nPrint only a single choice.\nAnswer:", "test", "A"),
            ("hard", "A hard question?\nA) x\nB) y\nAnswer:", "test", "B")]:
        rows[qid] = {"question_id": qid, "group_id": qid, "text": text, "is_original": True, "split": split,
                     "source": "test-fixture", "gold_answer": gold,
                     "answers": {STRONG: {"answer": gold + ")", "cost_usd": 0.1},
                                 WEAK: {"answer": "A", "cost_usd": 0.01}}}
    return rows


@pytest.fixture
def client(tmp_path):
    data, router = records(), dashboard.MemoRouter(FakeRouter())
    calibration = calibrate(data, router)
    app = dashboard.create_app(data, router, calibration, "digest", FakeEmbedder(), tmp_path)
    return TestClient(app), data, tmp_path


def test_split_question_drops_the_answer_format_instruction():
    stem, options = dashboard.split_question(records()["bread"]["text"])
    assert stem == "Is the bread vegan?" and options == ["A) Yes", "B) No"]


def test_wilson_range():
    low, high = dashboard.wilson(50, 100)
    assert low == pytest.approx(0.4038, abs=1e-3) and high == pytest.approx(0.5962, abs=1e-3)
    assert dashboard.wilson(0, 0) == (None, None)


def test_page_is_served(client):
    response = client[0].get("/")
    assert response.status_code == 200 and "CacheShift" in response.text


def test_a_full_run_matches_the_report_built_from_its_own_log(client):
    http, data, run_dir = client
    session = http.post("/api/session", json={"setting": "0.90"}).json()
    test = {qid: row for qid, row in data.items() if row["split"] == "test"}
    assert session["total"] == len(request_stream(test, dashboard.SEED)) and session["position"] == 0
    events = []
    while True:
        out = http.post(f"/api/session/{session['id']}/step", json={"count": 3}).json()
        events += out["events"]
        if out["done"]:
            break
    t = out["totals"]
    assert t["requests"] == session["total"] == len(events)
    sunday_hits = [e for e in events if e["question_id"] == "sun" and e["cache_hit"]]
    assert sunday_hits and all(e["wrong_question"] and e["matched_text"] == "When do you close on Saturday?"
                               for e in sunday_hits)

    log = report.read_log(run_dir / session["log"])
    built = report.build(log, data, 0.5, samples=20)
    r = built["rates"]
    assert t["hits"] / t["requests"] == pytest.approx(r["hit_rate"]["estimate"])
    assert t["accuracy"] == pytest.approx(r["accuracy"]["estimate"])
    assert t["usd_per_1000"] == pytest.approx(r["usd_per_1000"]["estimate"])
    assert t["share"] == pytest.approx(r["strong_share_of_routed"]["estimate"])
    assert t["wrong_question"] / t["requests"] == pytest.approx(r["wrong_question_rate"]["estimate"])
    assert t["no_cache_cost"] >= t["cost"]

    page = http.get(f"/api/session/{session['id']}/report")
    assert page.status_code == 200 and "CacheShift live demo, cache at 0.90" in page.text


def test_no_cache_costs_exactly_what_the_no_cache_estimate_says(client):
    http = client[0]
    session = http.post("/api/session", json={"setting": "off"}).json()
    out = http.post(f"/api/session/{session['id']}/step", json={"count": 50}).json()
    t = out["totals"]
    assert out["done"] and t["hits"] == 0 and t["no_cache_cost"] == pytest.approx(t["cost"])
    assert t["wrong_from_cache"] == 0


def test_bad_requests_are_refused(client):
    http = client[0]
    assert http.post("/api/session", json={"setting": "0.5"}).status_code == 400
    session = http.post("/api/session", json={"setting": "0.95"}).json()
    assert http.post(f"/api/session/{session['id']}/step", json={"count": 0}).status_code == 422
    assert http.post(f"/api/session/{session['id']}/step", json={"count": dashboard.MAX_STEP + 1}).status_code == 422
    assert http.get(f"/api/session/{session['id']}/report").status_code == 400   # nothing sent yet
    newer = http.post("/api/session", json={"setting": "0.80"}).json()
    assert http.post(f"/api/session/{session['id']}/step", json={"count": 1}).status_code == 404  # replaced
    assert http.post(f"/api/session/{newer['id']}/step", json={"count": 1}).status_code == 200


def test_share_verdict_says_when_there_are_too_few_questions():
    session = dashboard.Session.__new__(dashboard.Session)
    session.calibration = {"target_strong_share": 0.5}
    base = dict(requests=0, hits=0, routed=0, strong=0, weak=0, correct=0, cost=0.0, no_cache_cost=0.0,
                all_strong_cost=0.0, wrong_question=0, wrong_question_wrong=0, repeated_wrong=0)
    for routed, strong, verdict in [(0, 0, "waiting"), (100, 55, "too-few"), (20000, 10100, "within"),
                                    (20000, 12000, "outside")]:
        session.totals = dict(base, requests=routed, routed=routed, strong=strong)
        assert session.summary()["share_verdict"] == verdict
