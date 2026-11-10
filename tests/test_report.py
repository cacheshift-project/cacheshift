import json

import pytest

from cacheshift import report
from cacheshift.replay_gateway import STRONG, WEAK

ROOT = report.DATASET.parents[2]
DEMO = ROOT / "experiments/results/replay-demo-20261004"


def records():
    """Four one-question groups; q1/q2 are near-twins with different answers."""
    rows = {}
    for qid, gold, text in (("q1", "A", "What time do you close on Saturday?"),
                            ("q2", "B", "What time do you close on Sunday? <b>bold</b>"),
                            ("q3", "C", "Do you sell cookies?"), ("q4", "D", "Is there parking?")):
        rows[qid] = {"question_id": qid, "group_id": f"g-{qid}", "split": "test", "text": text, "gold_answer": gold,
                     "answers": {STRONG: {"answer": gold, "cost_usd": 0.01}, WEAK: {"answer": "E", "cost_usd": 0.001}}}
    return rows


def event(qid, *, hit=False, matched=None, similarity=None, route="strong", answer=None, cost=None, config="c1"):
    rows = records()
    if answer is None:
        answer = rows[qid]["gold_answer"] if route != "weak" else "E"
    if cost is None:
        cost = 0.0 if hit else (0.01 if route == "strong" else 0.001)
    return {"question_id": qid, "cache_hit": hit, "route": "cache" if hit else route, "answer": answer,
            "cost_usd": cost, "matched_question_id": matched if hit else None,
            "similarity": similarity if hit else None, "config_id": config}


def semantic_run():
    return [event("q1"),                                                     # strong, correct
            event("q2", hit=True, matched="q1", similarity=0.94, answer="A"),  # wrong question, wrong answer
            event("q3", route="weak"),                                       # weak, wrong ("E")
            event("q3", hit=True, matched="q3", similarity=1.0, answer="E"),   # repeated wrong answer
            event("q4"),                                                     # strong, correct
            event("q4", hit=True, matched="q4", similarity=1.0, answer="D")]   # correct reuse


def test_totals_and_rates_classify_every_kind_of_cached_answer():
    out = report.build(semantic_run(), records(), planned_share=0.5, samples=200)
    t, r = out["totals"], out["rates"]
    assert (t["requests"], t["hits"], t["routed"], t["strong"], t["correct"]) == (6, 3, 3, 2, 3)
    assert (t["wrong_question"], t["wrong_question_wrong"], t["repeated_wrong"]) == (1, 1, 1)
    assert t["cost"] == pytest.approx(0.021) and t["all_strong_cost"] == pytest.approx(0.06)
    assert r["hit_rate"]["estimate"] == pytest.approx(0.5)
    assert r["accuracy"]["estimate"] == pytest.approx(0.5)
    assert r["strong_share_of_routed"]["estimate"] == pytest.approx(2 / 3)
    assert r["drift_from_plan"]["estimate"] == pytest.approx(2 / 3 - 0.5)
    assert r["usd_per_1000"]["estimate"] == pytest.approx(3.5)
    assert r["saving_vs_all_strong"]["estimate"] == pytest.approx(1 - 0.021 / 0.06)
    for entry in r.values():
        low, high = entry["ci95"]
        assert low <= entry["estimate"] + 1e-12 and entry["estimate"] <= high + 1e-12
    [example] = out["examples"]
    assert example["question_id"] == "q2" and example["matched_question_id"] == "q1"
    assert example["served_answer"] == "A" and example["correct_answer"] == "B"


def test_paired_comparison_with_a_fresh_run():
    fresh = [event("q1"), event("q2"), event("q3", route="weak"), event("q3", route="weak"), event("q4"), event("q4")]
    out = report.build(semantic_run(), records(), planned_share=None, fresh_events=fresh, samples=200)
    assert out["fresh"]["accuracy"]["estimate"] == pytest.approx(4 / 6)
    assert out["paired"]["accuracy_change"]["estimate"] == pytest.approx(3 / 6 - 4 / 6)
    assert out["paired"]["strong_share_change"]["estimate"] == pytest.approx(2 / 3 - 4 / 6)
    assert "drift_from_plan" not in out["rates"]
    with pytest.raises(ValueError, match="same question groups"):
        report.build(semantic_run(), records(), None, fresh_events=fresh[:2], samples=50)


def test_read_log_rejects_other_files_and_mixed_runs(tmp_path):
    good = tmp_path / "run.jsonl"
    good.write_text("\n".join(json.dumps(e) for e in semantic_run()) + "\n")
    assert len(report.read_log(good)) == 6
    mixed = tmp_path / "mixed.jsonl"
    mixed.write_text(json.dumps(event("q1")) + "\n" + json.dumps(event("q4", config="c2")) + "\n")
    with pytest.raises(ValueError, match="mixes 2 gateway configurations"):
        report.read_log(mixed)
    other = tmp_path / "other.jsonl"
    other.write_text(json.dumps({"question_id": "q1"}) + "\n")
    with pytest.raises(ValueError, match="missing"):
        report.read_log(other)


def test_html_escapes_text_and_shows_the_wrong_question_example():
    out = report.build(semantic_run(), records(), planned_share=0.5, samples=50)
    page = report.render_html(out, "Test <report>", "run.jsonl")
    assert "Test &lt;report&gt;" in page and "<b>bold</b>" not in page and "&lt;b&gt;bold&lt;/b&gt;" in page
    assert "What time do you close on Saturday?" in page and "similarity 0.94" in page
    assert "Drifted from your plan" in page or "No clear drift from your plan" in page
    assert "(50 resamples)" in page


def test_cli_on_the_committed_sprint1_gateway_run_matches_its_own_summary(tmp_path, capsys):
    out = tmp_path / "report.html"
    report.main(["--log", str(DEMO / "exact_cache.jsonl"), "--fresh-log", str(DEMO / "no_cache.jsonl"),
                 "--config", str(DEMO / "report.json"), "--out", str(out)])
    saved = json.loads(out.with_suffix(".json").read_text())
    summary = json.loads((DEMO / "report.json").read_text())["runs"]["exact_cache"]["summary"]
    assert saved["totals"]["hits"] == summary["cache_hits"]
    assert saved["totals"]["strong"] == summary["strong_calls"]
    assert saved["totals"]["cost"] == pytest.approx(summary["historical_model_cost_usd"])
    assert saved["rates"]["strong_share_of_routed"]["estimate"] == pytest.approx(summary["strong_share_of_routed"])
    assert saved["planned_strong_share"] == summary["planned_strong_share"]
    assert out.read_text().startswith("<!doctype html>")
    assert "Expensive-model share of routed requests" in capsys.readouterr().out
