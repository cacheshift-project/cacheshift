import importlib.util
import json
from pathlib import Path

import anthropic
import httpx
import httpx2  # the Anthropic SDK's HTTP library
from openai import AuthenticationError
import pytest

spec = importlib.util.spec_from_file_location("check_api", Path(__file__).resolve().parents[1] / "scripts/check_api.py")
check = importlib.util.module_from_spec(spec)
spec.loader.exec_module(check)


def test_one_real_sdk_request_with_mock_transport_and_no_secrets(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text('OPENAI_API_KEY="fake-test-key"\nOPENAI_MODEL=test-model\n')
    calls = []

    def handle(request):
        calls.append(request)
        assert str(request.url) == "https://api.openai.com/v1/chat/completions"
        assert request.headers["Authorization"] == "Bearer fake-test-key"
        payload = json.loads(request.content)
        assert payload["max_completion_tokens"] == 32 and payload["store"] is False
        return httpx.Response(200, json={"id": "test", "created": 0, "object": "chat.completion",
                              "model": "test-model", "choices": [{"index": 0,
                              "message": {"role": "assistant", "content": "OK"}, "finish_reason": "stop"}]})

    real_client = httpx.Client
    def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        return real_client(transport=httpx.MockTransport(handle), **kwargs)
    monkeypatch.setattr(check, "Client", factory)
    report = check.check_api(path)
    assert len(calls) == 1 and report["status"] == "passed"
    assert "fake-test-key" not in json.dumps(report)


def test_missing_settings_fail_before_request(tmp_path):
    with pytest.raises(ValueError, match="No .env"):
        check.check_api(tmp_path / "absent")
    path = tmp_path / ".env"
    path.write_text("OPENAI_API_KEY=\n")
    with pytest.raises(ValueError, match="Set OPENAI_API_KEY"):
        check.check_api(path)


def test_authentication_error_is_not_retried(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("OPENAI_API_KEY=fake\nOPENAI_MODEL=test\n")
    calls = []
    def handle(request):
        calls.append(request)
        return httpx.Response(401, json={"error": {"message": "secret-error-body"}})
    real_client = httpx.Client
    monkeypatch.setattr(check, "Client", lambda **kwargs: real_client(transport=httpx.MockTransport(handle), **kwargs))
    with pytest.raises(AuthenticationError):
        check.check_api(path)
    assert len(calls) == 1


def test_cli_sanitizes_provider_errors(monkeypatch, capsys):
    def fail(*args):
        request = httpx.Request("POST", "https://api.openai.com/v1/chat/completions")
        raise AuthenticationError("secret-key-must-not-appear", response=httpx.Response(401, request=request), body=None)
    monkeypatch.setattr(check, "check_api", fail)
    monkeypatch.setattr("sys.argv", ["check_api.py"])
    with pytest.raises(SystemExit) as exc:
        check.main()
    assert exc.value.code == 1
    output = capsys.readouterr()
    assert "401" in output.err and "secret-key" not in output.err


def test_anthropic_one_request_with_mock_transport_and_no_secrets(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text('ANTHROPIC_API_KEY="fake-anthropic-key"\nANTHROPIC_MODEL=test-claude\n')
    calls = []

    def handle(request):
        calls.append(request)
        assert str(request.url) == "https://api.anthropic.com/v1/messages"
        assert "fake-anthropic-key" in (request.headers.get("x-api-key", "") + request.headers.get("authorization", ""))
        payload = json.loads(request.content)
        assert payload["max_tokens"] == 32 and payload["model"] == "test-claude"
        assert payload["messages"] == [{"role": "user", "content": "Reply with OK."}]
        return httpx2.Response(200, json={"id": "msg_test", "type": "message", "role": "assistant",
                              "model": "test-claude", "content": [{"type": "text", "text": "OK"}],
                              "stop_reason": "end_turn", "stop_sequence": None,
                              "usage": {"input_tokens": 11, "output_tokens": 4}})

    real_client = httpx2.Client
    def factory(**kwargs):
        assert kwargs["follow_redirects"] is False
        return real_client(transport=httpx2.MockTransport(handle), **kwargs)
    monkeypatch.setattr(check, "AnthropicHttpClient", factory)
    report = check.check_api(path, provider="anthropic")
    assert len(calls) == 1 and report["status"] == "passed"
    assert report["provider"] == "anthropic" and report["request_id"] == "msg_test"
    assert report["usage"]["output_tokens"] == 4
    assert "fake-anthropic-key" not in json.dumps(report)


def test_anthropic_missing_settings_and_empty_reply(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("OPENAI_API_KEY=fake\nOPENAI_MODEL=test\n")
    with pytest.raises(ValueError, match="Set ANTHROPIC_API_KEY and ANTHROPIC_MODEL"):
        check.check_api(path, provider="anthropic")
    path.write_text("ANTHROPIC_API_KEY=fake\nANTHROPIC_MODEL=test\n")
    def handle(request):
        return httpx2.Response(200, json={"id": "msg_empty", "type": "message", "role": "assistant",
                              "model": "test", "content": [], "stop_reason": "max_tokens",
                              "stop_sequence": None, "usage": {"input_tokens": 11, "output_tokens": 32}})
    real_client = httpx2.Client
    monkeypatch.setattr(check, "AnthropicHttpClient", lambda **kwargs: real_client(transport=httpx2.MockTransport(handle), **kwargs))
    with pytest.raises(ValueError, match="without text"):
        check.check_api(path, provider="anthropic")


def test_anthropic_authentication_error_is_not_retried(tmp_path, monkeypatch):
    path = tmp_path / ".env"
    path.write_text("ANTHROPIC_API_KEY=fake\nANTHROPIC_MODEL=test\n")
    calls = []
    def handle(request):
        calls.append(request)
        return httpx2.Response(401, json={"type": "error", "error": {"type": "authentication_error",
                                                                    "message": "secret-error-body"}})
    real_client = httpx2.Client
    monkeypatch.setattr(check, "AnthropicHttpClient", lambda **kwargs: real_client(transport=httpx2.MockTransport(handle), **kwargs))
    with pytest.raises(anthropic.AuthenticationError):
        check.check_api(path, provider="anthropic")
    assert len(calls) == 1


def test_cli_sanitizes_anthropic_errors(monkeypatch, capsys):
    seen = {}
    def fail(env, model, provider):
        seen["provider"] = provider
        request = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")
        raise anthropic.AuthenticationError("secret-key-must-not-appear",
                                            response=httpx2.Response(401, request=request), body=None)
    monkeypatch.setattr(check, "check_api", fail)
    monkeypatch.setattr("sys.argv", ["check_api.py", "--provider", "anthropic"])
    with pytest.raises(SystemExit) as exc:
        check.main()
    assert exc.value.code == 1 and seen["provider"] == "anthropic"
    output = capsys.readouterr()
    assert "401" in output.err and "secret-key" not in output.err
