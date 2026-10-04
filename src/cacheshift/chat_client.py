"""Minimal app client shared by the example and compatibility demo."""

from openai import OpenAI
from cacheshift.replay_gateway import STRONG


def ask(base_url, prompt):
    with OpenAI(base_url=base_url, api_key="local-replay", max_retries=0, timeout=120) as client:
        return client.chat.completions.create(
            model=STRONG, messages=[{"role": "user", "content": prompt}]
        )
