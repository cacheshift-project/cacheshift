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
