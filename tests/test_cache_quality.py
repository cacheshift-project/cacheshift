"""Story 2: semantic cache, hit labels and the hand-check tool. No model downloads."""

import csv
import importlib.util
import json
from pathlib import Path

import numpy as np
import pytest

from cacheshift.cache_quality import replay, same_question, summarize
from cacheshift.semantic_cache import SemanticCache

SPEC = importlib.util.spec_from_file_location("hand_check", Path(__file__).resolve().parents[1] / "tools" / "hand_check.py")
hand_check = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hand_check)

STRONG = "gpt-4-1106-preview"


def unit(*values):
    v = np.array(values, dtype=np.float32)
    return v / np.linalg.norm(v)


VECTORS = {
    "q1": unit(1, 0, 0),
    "q2": unit(0.98, 0.2, 0),   # a near twin of q1 with a different answer
    "q3": unit(0, 0, 1),
}


def row(qid, gold, answer, group=None, original=True):
    return {"question_id": qid, "group_id": group or qid, "text": qid, "is_original": original,
            "gold_answer": gold, "answers": {STRONG: {"answer": answer}}}


def records():
    return {"q1": row("q1", "A", "A"), "q2": row("q2", "B", "B"), "q3": row("q3", "C", "D)")}


def test_exact_cache_hits_only_identical_text():
    cache = SemanticCache(VECTORS.get, None)
    cache.insert("q1", {"answer": "A"})
    assert cache.lookup("q1") == ({"answer": "A"}, 1.0)
    assert cache.lookup("q2") == (None, None)


def test_threshold_controls_semantic_hits():
    loose, strict = SemanticCache(VECTORS.get, 0.9), SemanticCache(VECTORS.get, 0.99)
    for cache in (loose, strict):
        cache.insert("q1", {"answer": "A"})
    assert loose.lookup("q2")[0] == {"answer": "A"}
    entry, similarity = strict.lookup("q2")
    assert entry is None and 0.9 < similarity < 0.99


def test_rejects_bad_threshold():
    with pytest.raises(ValueError):
        SemanticCache(VECTORS.get, 1.5)


def test_same_question_rules():
    a, twin = row("a", "A", "A", group="stem"), row("b", "B", "B", group="stem")
    rewording = row("c", "A", "A", group="stem", original=False)
    assert same_question(a, a)
    assert not same_question(a, twin)          # two originals sharing a stem are different items
    assert same_question(rewording, a)


def test_replay_labels_each_kind_of_hit():
    recs = records()
    events = replay(recs, ["q1", "q2", "q3", "q3", "q1"], SemanticCache(VECTORS.get, 0.9), STRONG)
    labels = [e["label"] for e in events]
    assert labels == ["miss", "false_hit_error", "miss", "inherited_error", "hit_ok"]
    assert events[1]["matched_question_id"] == "q1" and events[1]["served_answer"] == "A"


def test_false_hit_can_be_right_by_luck():
    recs = records()
    recs["q2"]["gold_answer"] = "A"
    events = replay(recs, ["q1", "q2"], SemanticCache(VECTORS.get, 0.9), STRONG)
    assert events[1]["label"] == "false_hit_lucky"


def test_summary_rates_and_intervals():
    recs = records()
    events = replay(recs, ["q1", "q2", "q3", "q3", "q1"], SemanticCache(VECTORS.get, 0.9), STRONG)
    report = summarize(events, recs, seed=1, samples=200)
    assert report["counts"]["requests"] == 5 and report["counts"]["hits"] == 3
    assert report["false_hit_rate"]["estimate"] == pytest.approx(0.2)
    assert report["inherited_error_rate"]["estimate"] == pytest.approx(0.2)
    # q2 would have been right fresh; the false hit made it wrong. Inherited errors cost nothing in replay.
    assert report["accuracy_change"]["estimate"] == pytest.approx(-0.2)
    lo, hi = report["accuracy_change"]["ci95"]
    assert lo <= -0.2 <= hi


def test_hand_check_sheet_is_blind_and_scores(tmp_path):
    recs = records()
    data = tmp_path / "questions.jsonl"
    data.write_text("".join(json.dumps(r) + "\n" for r in recs.values()))
    events = replay(recs, ["q1", "q2", "q3", "q3", "q1"], SemanticCache(VECTORS.get, 0.9), STRONG)
    hits = tmp_path / "hits.jsonl"
    hits.write_text("".join(json.dumps(dict(e, model=STRONG, setting="cos>=0.90")) + "\n" for e in events if e["cache_hit"]))
    sheet, key = tmp_path / "sheet.csv", tmp_path / "key.json"
    hand_check.sample(hits, data, sheet, key, n=50, seed=0)
    rows = list(csv.DictReader(sheet.open()))
    assert len(rows) == 3 and "label" not in rows[0] and rows[0]["same_question"] == ""
    truth = json.loads(key.read_text())["items"]
    for r in rows:   # a perfect reviewer
        r["same_question"] = "Y" if truth[r["item"]]["same_question"] else "N"
        r["served_correct"] = "Y" if truth[r["item"]]["served_correct"] else "N"
    with sheet.open("w", newline="") as out:
        writer = csv.DictWriter(out, fieldnames=hand_check.SHEET_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    result = hand_check.score(sheet, key)
    assert result["both_labels"]["rate"] == 1.0 and result["passes_90_percent"]


def test_hand_check_rejects_blank_answers(tmp_path):
    with pytest.raises(ValueError):
        hand_check.parse_yes_no("", "1", "same_question")
