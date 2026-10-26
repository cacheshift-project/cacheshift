"""Make exactly one small OpenAI or Anthropic request using a local .env; never print secrets."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from httpx import Client
from dotenv import dotenv_values
from openai import APIConnectionError, APIStatusError, OpenAI

try:  # Optional until someone checks the Anthropic key.
    from anthropic import Anthropic
    from anthropic import DefaultHttpxClient as AnthropicHttpClient  # SDK 2.x uses httpx2, not httpx
    from anthropic import APIConnectionError as AnthropicConnectionError
    from anthropic import APIStatusError as AnthropicStatusError
except ImportError:
    Anthropic = AnthropicHttpClient = None

    class AnthropicStatusError(Exception):
        """Placeholder; never raised when the SDK is absent."""

    AnthropicConnectionError = AnthropicStatusError

# Fixed official origins and the .env names each provider reads.
PROVIDERS = {
    "openai": {"key": "OPENAI_API_KEY", "model": "OPENAI_MODEL", "base_url": "https://api.openai.com/v1"},
    "anthropic": {"key": "ANTHROPIC_API_KEY", "model": "ANTHROPIC_MODEL", "base_url": "https://api.anthropic.com"},
}
PROMPT = [{"role": "user", "content": "Reply with OK."}]
MAX_OUTPUT_TOKENS = 32


class CheckError(ValueError):
    """Messages controlled by this script and safe to display."""


def _call_openai(key, model, base_url):
    with OpenAI(api_key=key, base_url=base_url, max_retries=0,
                http_client=Client(timeout=30, follow_redirects=False)) as client:
        response = client.chat.completions.create(
            model=model, messages=PROMPT, max_completion_tokens=MAX_OUTPUT_TOKENS, store=False,
        )
    text = response.choices[0].message.content if response.choices else None
    usage = response.usage.model_dump() if response.usage else None
    return text, response.model, response.id, usage


def _call_anthropic(key, model, base_url):
    if Anthropic is None:
        raise CheckError("Install the Anthropic SDK first: pip install -e \".[dev]\"")
    with Anthropic(api_key=key, base_url=base_url, max_retries=0,
                   http_client=AnthropicHttpClient(timeout=30, follow_redirects=False)) as client:
        response = client.messages.create(model=model, messages=PROMPT, max_tokens=MAX_OUTPUT_TOKENS)
    text = "".join(block.text for block in response.content if block.type == "text")
    usage = response.usage.model_dump() if response.usage else None
    return text, response.model, response.id, usage


def check_api(env_path, model=None, provider="openai"):
    if provider not in PROVIDERS:
        raise CheckError(f"Unknown provider; choose one of: {', '.join(PROVIDERS)}.")
    if not Path(env_path).is_file():
        raise CheckError("No .env file found. Copy .env.example and fill it locally.")
    names = PROVIDERS[provider]
    values = dotenv_values(env_path, interpolate=False)
    key = values.get(names["key"])
    selected = model or values.get(names["model"])
    if not key or not key.strip() or not selected or not selected.strip():
        raise CheckError(f"Set {names['key']} and {names['model']} in .env, or supply --model.")
    # One bounded billable request: no redirects, no retries.
    call = _call_openai if provider == "openai" else _call_anthropic
    text, returned_model, request_id, usage = call(key, selected, names["base_url"])
    if not text or not text.strip():
        raise CheckError("The API replied without text; authentication alone does not prove a usable completion.")
    return {"status": "passed", "provider": provider, "model": returned_model,
            "request_id": request_id, "timestamp": datetime.now(timezone.utc).isoformat(),
            "usage": usage}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--provider", choices=sorted(PROVIDERS), default="openai")
    parser.add_argument("--model", help="A text model available to your account (overrides .env)")
    parser.add_argument("--output", type=Path, help="Optional new file for sanitized success evidence")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.exit(2, "Output exists; choose a new evidence file.\n")
    if args.output and not args.output.parent.is_dir():
        parser.exit(2, "Create the output directory before making the test call.\n")
    try:
        result = check_api(args.env, args.model, args.provider)
    except (APIStatusError, AnthropicStatusError) as exc:
        parser.exit(1, f"API returned HTTP {exc.status_code}. Check key permissions, model access and billing.\n")
    except (APIConnectionError, AnthropicConnectionError):
        parser.exit(1, "Could not reach the API within the timeout. No automatic retry was made.\n")
    except CheckError as exc:
        parser.exit(1, str(exc) + "\n")
    except (ValueError, OSError):
        parser.exit(1, "Invalid local settings or file access; check .env without sharing its contents.\n")
    payload = json.dumps(result, indent=2) + "\n"
    if args.output:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(payload)
    print(payload, end="")


if __name__ == "__main__":
    main()
