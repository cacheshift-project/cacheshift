"""Make exactly one small OpenAI request using a local .env; never print secrets."""

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

from httpx import Client
from dotenv import dotenv_values
from openai import APIConnectionError, APIStatusError, OpenAI


class CheckError(ValueError):
    """Messages controlled by this script and safe to display."""


def check_api(env_path, model=None):
    if not Path(env_path).is_file():
        raise CheckError("No .env file found. Copy .env.example and fill it locally.")
    values = dotenv_values(env_path, interpolate=False)
    key = values.get("OPENAI_API_KEY")
    selected = model or values.get("OPENAI_MODEL")
    if not key or not key.strip() or not selected or not selected.strip():
        raise CheckError("Set OPENAI_API_KEY and OPENAI_MODEL in .env, or supply --model.")
    # Fixed official origin, no redirects or retries; one bounded billable request.
    with OpenAI(api_key=key, base_url="https://api.openai.com/v1", max_retries=0,
                http_client=Client(timeout=30, follow_redirects=False)) as client:
        response = client.chat.completions.create(
            model=selected, messages=[{"role": "user", "content": "Reply with OK."}],
            max_completion_tokens=32, store=False,
        )
    if not response.choices or not response.choices[0].message.content:
        raise CheckError("The API replied without text; authentication alone does not prove a usable completion.")
    return {"status": "passed", "provider": "openai", "model": response.model,
            "request_id": response.id, "timestamp": datetime.now(timezone.utc).isoformat(),
            "usage": response.usage.model_dump() if response.usage else None}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--env", type=Path, default=Path(".env"))
    parser.add_argument("--model", help="Use a Chat Completions model available to your account")
    parser.add_argument("--output", type=Path, help="Optional new file for sanitized success evidence")
    args = parser.parse_args()
    if args.output and args.output.exists():
        parser.exit(2, "Output exists; choose a new evidence file.\n")
    if args.output and not args.output.parent.is_dir():
        parser.exit(2, "Create the output directory before making the test call.\n")
    try:
        result = check_api(args.env, args.model)
    except APIStatusError as exc:
        parser.exit(1, f"API returned HTTP {exc.status_code}. Check key permissions, model access and billing.\n")
    except APIConnectionError:
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
