import importlib.util
import json
from pathlib import Path

import httpx
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
