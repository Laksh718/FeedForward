"""One call to a hosted language model (Groq chat API) over HTTP. It only turns figures into words.

The key is read from GROQ_API_KEY in .env and is never printed or logged. If there is no key, no internet or the
service fails, LLMUnavailable is raised and the caller uses the template answer instead.
"""

import os

import httpx
from dotenv import load_dotenv

from feedforward import config as C

load_dotenv(C.PROJECT_ROOT / ".env")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
DEFAULT_MODEL = "openai/gpt-oss-20b"        # check this name is still available in your Groq console
TEMPERATURE = 0.2                           # low, so the same question gives nearly the same answer
MAX_TOKENS = 500                            # answers are short by design, plus room for the model's reasoning tokens
TIMEOUT_S = 20.0


class LLMUnavailable(RuntimeError):
    """No key, no network or the service refused the call."""


def is_configured() -> bool:
    """True when a key is present (it may still fail at call time)."""
    return bool(os.getenv("GROQ_API_KEY", "").strip())


def complete(messages: list[dict], transport: httpx.BaseTransport | None = None) -> str:
    """Send the messages once and return the reply text. `transport` is for tests only."""
    key = os.getenv("GROQ_API_KEY", "").strip()
    if not key:
        raise LLMUnavailable("GROQ_API_KEY is not set in .env")
    body = {"model": os.getenv("GROQ_MODEL", DEFAULT_MODEL), "messages": messages, "temperature": TEMPERATURE,
            "max_tokens": MAX_TOKENS, "reasoning_effort": "low"}
    try:
        with httpx.Client(timeout=TIMEOUT_S, transport=transport) as client:
            r = client.post(GROQ_URL, json=body, headers={"Authorization": f"Bearer {key}"})
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, ValueError) as exc:
        raise LLMUnavailable(f"the language model could not be reached ({type(exc).__name__})") from exc
