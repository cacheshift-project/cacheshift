from collections import Counter
import pytest

from cacheshift import uneven_repeats


def records(n=60):
    subjects = ["high_school_biology", "college_physics", "anatomy"]
    return {f"q{i}": {"question_id": f"q{i}", "subject": subjects[i % 3]} for i in range(n)}


def test_topic_levels_come_from_the_subject_name():
    assert uneven_repeats.level("elementary_mathematics") == "easy"
    assert uneven_repeats.level("high_school_physics") == "easy"
    assert uneven_repeats.level("professional_law") == "hard"
    assert uneven_repeats.level("college_medicine") == "hard"
    assert uneven_repeats.level("virology") == "other"


def test_streams_ask_every_question_once_and_skew_only_the_repeats():
    rows = records(600)
    uniform = uneven_repeats.weighted_stream(rows, "uniform")
    easy = uneven_repeats.weighted_stream(rows, "easy-repeat")
    for stream in (uniform, easy):
        assert len(stream) == 1200 and set(stream) == set(rows)
    u, e = (uneven_repeats.repeats_by_level(s, rows) for s in (uniform, easy))
    assert sum(u.values()) == sum(e.values()) == 600
    # easy questions are a third of the pool; weight 3 makes them about 3/5 of the repeats
    assert 0.25 < u["easy"] / 600 < 0.42 and 0.52 < e["easy"] / 600 < 0.68
    hard = uneven_repeats.repeats_by_level(uneven_repeats.weighted_stream(rows, "hard-repeat"), rows)
    assert hard["hard"] > u["hard"]
    assert uneven_repeats.weighted_stream(rows, "easy-repeat") == easy      # seeded


def test_retune_scale_crossfit_uses_the_other_half_for_every_group():
    from cacheshift import retune_scale

    recs = {f"q{i}": {"question_id": f"q{i}", "group_id": f"g{i}"} for i in range(40)}
    fit_a = {"fit_group_ids": [g for g in (f"g{i}" for i in range(40)) if __import__("cacheshift.retune_log", fromlist=["x"]).fit_half(g)]}
    cached = [{"question_id": q} for q in recs]
    after_a = [{"question_id": q, "tag": "A"} for q in recs]
    after_b = [{"question_id": q, "tag": "B"} for q in recs]
    chosen = []

    def fake_comparison(before, mixed, records, retune, planned):
        chosen.extend(mixed)
        assert retune["fit_group_ids"] == []
        return {"threshold_after": None}

    original = retune_scale.report.retune_comparison
    retune_scale.report.retune_comparison = fake_comparison
    try:
        retune_scale.crossfit(cached, after_a, after_b, recs, fit_a, 0.5)
    finally:
        retune_scale.report.retune_comparison = original
    fitted = set(fit_a["fit_group_ids"])
    # groups that cutoff A was fitted on are judged with cutoff B, and vice versa
    assert all((e["tag"] == "B") == (recs[e["question_id"]]["group_id"] in fitted) for e in chosen)


def test_reworded_prompt_swaps_only_the_question_and_keeps_the_options():
    from cacheshift import reworded_check

    prompt = ("Please answer with the letter of the correct answer.\n\nWhat is 2+2?\nA) 3\nB) 4\n"
              "Print only a single choice from \"A\" or \"B\" without explanation. Answer:")
    assert reworded_check.stem_of(prompt) == "What is 2+2?"
    new = reworded_check.reworded_prompt(prompt, "What is 2+2?", "Two plus two equals?")
    assert new.startswith("Please answer") and "Two plus two equals?\nA) 3\nB) 4" in new
    assert reworded_check.stem_of(new) == "Two plus two equals?"
    with pytest.raises(ValueError):
        reworded_check.reworded_prompt(prompt, "not there", "x")


def test_reworded_check_counts_own_matches_other_matches_and_misses():
    import numpy as np
    from cacheshift import reworded_check

    def row(qid, stem, gold):
        text = f"Please answer.\n\n{stem}\nA) x\nB) y\nPrint only a single choice."
        return {"question_id": qid, "split": "test", "text": text, "gold_answer": gold,
                "answers": {"m": {"answer": gold, "cost_usd": 0.0}}}
    records = {r["question_id"]: r for r in (row("a", "Alpha?", "A"), row("b", "Beta?", "B"), row("c", "Gamma?", "A"))}
    rewordings = [{"question_id": "a", "level": "easy", "original": "Alpha?", "reworded": "Alpha again?"},
                  {"question_id": "b", "level": "hard", "original": "Beta?", "reworded": "Not beta at all?"}]
    vectors = {"Alpha?": [1, 0, 0], "Beta?": [0, 1, 0], "Gamma?": [0, 0, 1],
               "Alpha again?": [0.95, 0.312, 0], "Not beta at all?": [0, 0.5, 0.866]}

    def embed_many(texts):
        out = np.array([vectors[reworded_check.stem_of(t) if "\n" in t else t] for t in texts], dtype=np.float32)
        return out / np.linalg.norm(out, axis=1, keepdims=True)

    result = reworded_check.check(records, rewordings, embed_many, lambda text: text)
    s = result["by_setting"]
    assert s["0.90"] == {"caught_own_original": 1, "matched_other_question": 0, "other_question_possibly_wrong": 0,
                         "missed": 1, "n": 2}
    # at 0.80 the second rewording is closer to Gamma (0.866) than to its own Beta (0.5): a wrong-question match,
    # and Gamma's answer (A) is wrong for Beta (B)
    assert s["0.80"]["matched_other_question"] == 1 and s["0.80"]["other_question_possibly_wrong"] == 1


def test_score_cache_on_disk_is_reused_and_never_changes_a_score(tmp_path):
    from cacheshift.retune_scale import MemoRouter

    class Counting:
        calls = 0

        def score(self, text):
            Counting.calls += 1
            return {"router_score": len(text) / 100}

    path = tmp_path / "scores.jsonl"
    first = MemoRouter(Counting(), path)
    a = [first.score(t)["router_score"] for t in ("one", "three", "one")]
    assert Counting.calls == 2
    second = MemoRouter(Counting(), path)
    b = [second.score(t)["router_score"] for t in ("one", "three")]
    assert Counting.calls == 2 and b == a[:2]


def test_setting_finder_recommends_the_most_saving_setting_under_the_limit():
    import numpy as np
    from cacheshift import report, setting_finder
    from cacheshift.replay_gateway import STRONG, WEAK, calibrate

    texts = {"sat": "When do you close on Saturday?", "sun": "When do you close on Sunday?",
             "hard": "A hard question?", "x": "easy tuning", "y": "hard tuning"}
    records = {}
    for qid, text in texts.items():
        records[qid] = {"question_id": qid, "group_id": qid, "text": text, "is_original": True,
                        "split": "tuning" if qid in "xy" else "test", "gold_answer": "A" if qid != "sun" else "B",
                        "answers": {STRONG: {"answer": "A" if qid != "sun" else "B", "cost_usd": 0.1},
                                    WEAK: {"answer": "A", "cost_usd": 0.01}}}

    class Router:
        def score(self, text):
            return {"router_score": 0.9 if "hard" in text else 0.1}

    def embed(text):
        v = np.zeros(8, dtype=np.float32)
        known = [k for k, t in texts.items() if t == text]
        if not known:                 # a trimmed difference, e.g. "Sunday?": its own direction
            v[5 + len(text) % 3] = 1
            return v
        v[{"sat": 1, "sun": 2, "hard": 3}[known[0]]] = 1
        if text == texts["sun"]:      # Sunday is 0.92 alike to Saturday
            v = 0.92 * embed(texts["sat"]) + np.sqrt(1 - 0.92**2) * v
        return v.astype(np.float32)
    embed.model_name = "fake"

    router = Router()
    stream = ["sat", "sun", "hard", "sat", "sun", "hard"]
    out = setting_finder.sweep(stream, records, router, calibrate(records, router), embed, limit=0.0,
                               settings=(0.95, 0.90), samples=50)
    by = {row["label"]: row for row in out["rows"]}
    assert by["0.90"]["wrong_caused"] >= 1                     # Sunday gets Saturday's answer
    assert by["0.95"]["wrong_caused"] == 0
    assert out["recommended"] in ("0.95", "0.95 + difference check")
    built = report.build([{"question_id": "sat", "cache_hit": False, "route": "weak", "answer": "A", "cost_usd": 0.01,
                           "router_score": 0.1, "matched_question_id": None, "similarity": None, "config_id": "c"}],
                         records, 0.5, samples=10)
    built["settings"] = out
    page = report.render_html(built, "t", "run.jsonl")
    assert "Which cache setting is safe for your questions?" in page and "Recommended:" in page


def test_rebuilt_run_serves_hits_the_answer_their_match_got_under_the_new_cutoff():
    from cacheshift.replay_gateway import STRONG, WEAK
    from cacheshift.retune_splits import with_cutoff

    records = {q: {"answers": {STRONG: {"answer": f"{q}-strong", "cost_usd": 1.0},
                               WEAK: {"answer": f"{q}-weak", "cost_usd": 0.1}}} for q in ("a", "b")}
    events = [{"question_id": "a", "cache_hit": False, "router_score": 0.6, "route": "strong",
               "answer": "a-strong", "cost_usd": 1.0, "matched_question_id": None},
              {"question_id": "b", "cache_hit": True, "router_score": None, "route": "cache",
               "answer": "a-strong", "cost_usd": 0.0, "matched_question_id": "a"}]
    rebuilt = with_cutoff(events, records, 0.7)            # a now goes to the weak model
    assert rebuilt[0]["route"] == "weak" and rebuilt[0]["cost_usd"] == 0.1
    assert rebuilt[1]["answer"] == "a-weak" and rebuilt[1]["cost_usd"] == 0.0
