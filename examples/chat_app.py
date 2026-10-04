"""One client, change only --base-url to switch between compatible servers."""

import argparse
from pathlib import Path

from cacheshift.chat_client import ask


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000/v1")
    parser.add_argument("--prompt-file", type=Path, required=True)
    args = parser.parse_args()
    response = ask(args.base_url, args.prompt_file.read_text(encoding="utf-8"))
    print(response.choices[0].message.content)
