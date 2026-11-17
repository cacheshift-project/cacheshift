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
    assert "Drifted more than 3 points from your plan" in page   # 66.7% vs 50% planned
    assert "(50 resamples)" in page
    assert "within ±3 points of plan" in page and "amber" not in page   # no fresh run, so no accuracy pill


def test_drift_label_uses_the_story3_band_not_whether_the_range_excludes_zero():
    share = 2 / 3
    # Spencer's #52 example: +2.2 points with a range clear of zero is still within ±3, so not "Drifted".
    out = report.build(semantic_run(), records(), planned_share=share - 0.022, samples=200)
    assert out["rates"]["drift_from_plan"]["estimate"] == pytest.approx(0.022)
    assert out["within_band"] and out["drift_band"] == 0.03
    page = report.render_html(out, "t", "run.jsonl")
    assert "Within 3 points of your plan" in page and "Drifted" not in page
    assert "within the ±3-point band" in report.text_summary(out, "t")
    for planned, within in ((share - 0.03, True), (share + 0.03, True), (share - 0.031, False), (share + 0.031, False)):
        assert report.build(semantic_run(), records(), planned_share=planned, samples=20)["within_band"] is within


def test_cache_hit_without_matched_question_is_an_error(tmp_path):
    bad = dict(event("q4", hit=True, matched="q4", similarity=1.0, answer="D"), matched_question_id=None)
    log = tmp_path / "run.jsonl"
    log.write_text(json.dumps(event("q4")) + "\n" + json.dumps(bad) + "\n")
    with pytest.raises(ValueError, match=r"run.jsonl:2 is a cache hit without 'matched_question_id'"):
        report.read_log(log)
    missing = {key: value for key, value in bad.items() if key != "matched_question_id"}
    with pytest.raises(ValueError, match="no matched_question_id"):
        report.build([event("q4"), missing], records(), planned_share=None, samples=20)


def test_footer_states_the_amber_accuracy_threshold():
    fresh = [event("q1"), event("q2"), event("q3", route="weak"), event("q3", route="weak"), event("q4"), event("q4")]
    out = report.build(semantic_run(), records(), planned_share=None, fresh_events=fresh, samples=200)
    page = report.render_html(out, "t", "run.jsonl")
    assert "vs fresh answers" label is amber when the low end of its range is below -0.5 points" in page
    assert "within ±3 points of plan" not in page   # no plan given


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


# ---------- #49: re-tuning step ----------

def retune_records(groups=40):
    """Groups of one question; router scores spread evenly so a cutoff can hit any share."""
    rows = {}
    for i in range(groups):
        qid = f"r{i:02d}"
        rows[qid] = {"question_id": qid, "group_id": f"g-{qid}", "split": "test", "text": f"Question {i}?",
                     "gold_answer": "A",
                     "answers": {STRONG: {"answer": "A", "cost_usd": 0.01},
                                 WEAK: {"answer": "A" if i % 4 else "B", "cost_usd": 0.001}}}
    return rows


def routed_run(rows, cutoff):
    """Each question once (routed) and once more (exact cache hit); score = i / len."""
    events = []
    for i, qid in enumerate(sorted(rows)):
        score = i / len(rows)
        route = "strong" if score >= cutoff else "weak"
        model = STRONG if route == "strong" else WEAK
        answer = rows[qid]["answers"][model]["answer"]
        events.append({"question_id": qid, "cache_hit": False, "route": route, "answer": answer,
                       "cost_usd": rows[qid]["answers"][model]["cost_usd"], "router_score": score,
                       "matched_question_id": None, "similarity": None, "config_id": f"cut-{cutoff}"})
        events.append({"question_id": qid, "cache_hit": True, "route": "cache", "answer": answer, "cost_usd": 0.0,
                       "router_score": None, "matched_question_id": qid, "similarity": 1.0,
                       "config_id": f"cut-{cutoff}"})
    return events


def test_retune_fits_on_one_half_and_the_report_compares_on_the_other():
    from cacheshift import retune_log

    rows = retune_records()
    before = routed_run(rows, cutoff=0.2)                 # 80% expensive vs a 50% plan
    retune = retune_log.fit(before, rows, 0.5)
    fitted = set(retune["fit_group_ids"])
    assert fitted and retune["held_out_groups"] == len(rows) - len(fitted)
    assert all(retune_log.fit_half(group) for group in fitted)
    assert retune["fit_strong_share"] == pytest.approx(0.5, abs=0.05)
    after = routed_run(rows, cutoff=retune["threshold"])
    retune["previous_threshold"] = 0.2
    out = report.build(before, rows, 0.5, retuned_events=after, retune=retune, samples=200)
    x = out["retune"]
    held = [qid for qid in rows if rows[qid]["group_id"] not in fitted]
    assert x["held_out_groups"] == len(held) and x["held_out_requests"] == 2 * len(held)
    share = lambda cut: sum(int(q[1:]) / len(rows) >= cut for q in held) / len(held)
    assert x["before"]["strong_share_of_routed"]["estimate"] == pytest.approx(share(0.2))
    assert x["after"]["strong_share_of_routed"]["estimate"] == pytest.approx(share(retune["threshold"]))
    assert x["change"]["usd_per_1000"]["estimate"] < 0           # fewer expensive calls
    assert x["change"]["accuracy"]["estimate"] <= 0              # the weak model misses some
    assert x["after_within_band"] == (abs(share(retune["threshold"]) - 0.5) <= 0.03)
    page = report.render_html(out, "t", "run.jsonl")
    assert "Re-tune the router? (your call)" in page and "0.2000 → " in page
    assert "below -1.0 point (the margin agreed in #37)" in page
    assert "Re-tuning (new cutoff" in report.text_summary(out, "t")


def test_retune_inputs_are_checked():
    from cacheshift import retune_log

    rows = retune_records()
    before = routed_run(rows, cutoff=0.2)
    retune = retune_log.fit(before, rows, 0.5)
    with pytest.raises(ValueError, match="both the re-tuned log and the re-tune file"):
        report.build(before, rows, 0.5, retuned_events=before, samples=20)
    with pytest.raises(ValueError, match="same question stream"):
        report.build(before, rows, 0.5, retuned_events=before[::-1], retune=retune, samples=20)
    with pytest.raises(ValueError, match="different planned share"):
        report.build(before, rows, 0.4, retuned_events=before, retune=retune, samples=20)
    no_score = [dict(event, router_score=None) for event in before]
    with pytest.raises(ValueError, match="no valid router_score"):
        retune_log.fit(no_score, rows, 0.5)


def test_retune_cli_on_the_committed_sprint1_run_feeds_the_report(tmp_path, capsys):
    from cacheshift import retune_log

    out = tmp_path / "retune.json"
    retune_log.main(["--log", str(DEMO / "exact_cache.jsonl"), "--config", str(DEMO / "report.json"), "--out", str(out)])
    saved = retune_log.load(out)
    config = json.loads((DEMO / "report.json").read_text())["runs"]["exact_cache"]["config"]
    assert saved["target_strong_share"] == config["target_strong_share"]
    assert saved["previous_threshold"] == config["threshold"] and saved["log"] == "exact_cache.jsonl"
    assert "New cutoff" in capsys.readouterr().out
    # The same log as its own "re-tuned" run: nothing changes, and the report still renders.
    html = tmp_path / "report.html"
    report.main(["--log", str(DEMO / "exact_cache.jsonl"), "--config", str(DEMO / "report.json"),
                 "--retuned-log", str(DEMO / "exact_cache.jsonl"), "--retune", str(out), "--out", str(html)])
    change = json.loads(html.with_suffix(".json").read_text())["retune"]["change"]
    assert change["strong_share_of_routed"]["estimate"] == 0 and change["accuracy"]["estimate"] == 0
    with pytest.raises(SystemExit):
        report.main(["--log", str(DEMO / "exact_cache.jsonl"), "--retune", str(out), "--out", str(html)])
