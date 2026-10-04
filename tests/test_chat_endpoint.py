import json

from fastapi.testclient import TestClient
import pytest

from cacheshift.chat_client import ask
from cacheshift.demo import serve
from cacheshift.gateway import create_app
from cacheshift.replay_gateway import STRONG
from test_replay_gateway import engine


def body(**updates):
    return {"model": STRONG, "messages": [{"role": "user", "content": "easy"}], **updates}


def test_sdk_switches_only_address_and_logs_cache_hit(tmp_path):
    direct = engine(tmp_path / "direct", cache=False)
    direct.threshold = 0.0
    gateway = engine(tmp_path / "gateway")
    with serve(create_app(direct)) as direct_url, serve(create_app(gateway)) as gateway_url:
        assert ask(direct_url + "/v1", "easy").choices[0].message.content == "A"
        first = ask(gateway_url + "/v1", "easy")
        repeat = ask(gateway_url + "/v1", "easy")
    assert first.object == "chat.completion"
    assert first.choices[0].message.content == repeat.choices[0].message.content == "B"
    assert first.usage is None
    events = [json.loads(line) for line in gateway.log_path.read_text().splitlines()]
    assert [event["route"] for event in events] == ["weak", "cache"]
    assert repeat.id == "chatcmpl-" + events[1]["request_id"]


@pytest.mark.parametrize("changes", [
    {"stream": True}, {"n": 2}, {"temperature": 0}, {"model": "unknown"},
    {"messages": [{"role": "system", "content": "new context"}]},
    {"messages": [{"role": "user", "content": "easy"}] * 2},
    {"messages": [{"role": "user", "content": [{"type": "text", "text": "easy"}]}]},
])
def test_unsupported_chat_features_fail_before_routing(tmp_path, changes):
    gateway = engine(tmp_path)
    with TestClient(create_app(gateway)) as client:
        assert client.post("/v1/chat/completions", json=body(**changes)).status_code == 422
    assert not gateway.router.calls
    assert not gateway.log_path.read_text()


def test_unknown_or_ambiguous_prompts_are_not_replayed(tmp_path):
    gateway = engine(tmp_path)
    gateway.records["q2"]["text"] = "easy"
    with TestClient(create_app(gateway)) as client:
        for prompt in ("easy", "unknown", " easy"):
            response = client.post("/v1/chat/completions", json=body(messages=[{"role": "user", "content": prompt}]))
            assert response.status_code == 400
    assert not gateway.router.calls
