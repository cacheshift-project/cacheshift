import json
import math
from pathlib import Path
import socket

import pytest

from cacheshift.router import REVISION, LocalBERTRouter, strong_score
from cacheshift.score_router import read_questions


def test_score_direction_and_ties():
    assert strong_score([1000, 0, 0]) == 1.0
    assert strong_score([0, 1000, 0]) == 0.0  # tie is not a strong win
    assert strong_score([0, 0, 1000]) == 0.0
    assert strong_score([0, 0, 0]) == pytest.approx(1 / 3)
    assert strong_score([1002, 1001, 1000]) == pytest.approx(strong_score([2, 1, 0]))


@pytest.mark.parametrize("logits", [[1, 2], [math.nan, 0, 0], [math.inf, 0, 0]])
def test_invalid_logits_fail(logits):
    with pytest.raises(ValueError):
        strong_score(logits)


def test_batch_validation_needs_no_model():
    router = LocalBERTRouter.__new__(LocalBERTRouter)
    assert router.score_many([]) == []
    for batch in ([""], ["valid", None]):
        with pytest.raises(ValueError, match="nonempty"):
            router.score_many(batch)
    with pytest.raises(ValueError, match="batch_size"):
        router.score_many(["valid"], batch_size=0)


@pytest.mark.parametrize("rows", [[], [{"question_id": "x", "text": " "}],
                                     [{"question_id": "x", "text": "q"}] * 2])
def test_bad_input_fails_before_model_download(tmp_path, rows):
    path = tmp_path / "questions.jsonl"
    path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
    with pytest.raises(ValueError):
        read_questions(path)


def test_cached_checkpoint_needs_no_network(monkeypatch):
    cache = Path(__file__).resolve().parents[1] / "data/cache/routellm"
    weights = cache / "models--routellm--bert" / "snapshots" / REVISION / "model.safetensors"
    if not weights.exists():
        pytest.skip("Optional integration test requires downloaded checkpoint")
    pytest.importorskip("torch")
    pytest.importorskip("transformers")

    def reject_network(*args, **kwargs):
        pytest.fail("Offline router attempted network access")

    monkeypatch.setattr(socket.socket, "connect", reject_network)
    router = LocalBERTRouter(cache, offline=True)
    first = router.score("What is the boiling point of water at sea level?")
    assert 0 <= first["router_score"] <= 1
    assert first == router.score("What is the boiling point of water at sea level?")
    assert not first["truncated"]
    prompts = ["What is the boiling point of water at sea level?", "Which planet is closest to the Sun?"]
    batch = router.score_many(prompts)
    assert [r["router_score"] for r in batch] == pytest.approx(
        [router.score(p)["router_score"] for p in prompts], abs=1e-5)
    assert batch[0]["used_tokens"] == first["used_tokens"]
