"""One request to a hosted language model over HTTP per answer. It only turns figures into words.

Google Gemini only (GEMINI_API_KEY, model GEMINI_MODEL). The key is read from .env (or the host's environment) and is
never printed or logged. Exactly one request is sent per answer: no retries and no second model. If there is no key, no internet or the service fails,
LLMUnavailable is raised and the caller uses the template answer instead.
"""

import os

import httpx
from dotenv import load_dotenv

from feedforward import config as C

load_dotenv(C.PROJECT_ROOT / ".env")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_DEFAULT_MODEL = "gemini-3.1-flash-lite"   # change with GEMINI_MODEL
TEMPERATURE = 0.2                                # low, so the same question gives nearly the same answer
MAX_TOKENS = 500                                 # answers are short by design
GEMINI_THINKING_TOKENS = 2048                    # newer Gemini models think first, and that counts against the output limit
TIMEOUT_S = 20.0                                 # one request


class LLMUnavailable(RuntimeError):
    """No key, no network or the service refused the call."""


def _key(name: str) -> str:
    return os.getenv(name, "").strip()


def is_configured() -> bool:
    """True when GEMINI_API_KEY is set (the request may still fail at call time)."""
    return bool(_key("GEMINI_API_KEY"))


def _gemini_body(messages: list[dict], model: str) -> dict:
    """Chat messages (system, user, assistant) in Gemini's shape: a system instruction plus user and model turns."""
    system = "\n\n".join(m["content"] for m in messages if m["role"] == "system")
    contents = [{"role": "model" if m["role"] == "assistant" else "user", "parts": [{"text": m["content"]}]}
                for m in messages if m["role"] != "system"]
    config = {"temperature": TEMPERATURE, "maxOutputTokens": GEMINI_THINKING_TOKENS}
    if "2.5-flash" in model:   # 2.5 Flash can skip its hidden reasoning, which this short rewording does not need
        config.update(maxOutputTokens=MAX_TOKENS, thinkingConfig={"thinkingBudget": 0})
    body = {"contents": contents, "generationConfig": config}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return body


def _gemini_text(data: dict) -> str:
    parts = data["candidates"][0]["content"]["parts"]
    text = "".join(p.get("text", "") for p in parts if not p.get("thought")).strip()
    if not text:
        raise ValueError("empty reply")
    return text


def _gemini(messages: list[dict], client: httpx.Client) -> str:
    """The one Gemini request."""
    model = _key("GEMINI_MODEL") or GEMINI_DEFAULT_MODEL
    r = client.post(GEMINI_URL.format(model=model), json=_gemini_body(messages, model),
                    headers={"x-goog-api-key": _key("GEMINI_API_KEY")})
    r.raise_for_status()
    return _gemini_text(r.json())


def complete(messages: list[dict], transport: httpx.BaseTransport | None = None) -> str:
    """Send the messages and return the reply text. `transport` is for tests only."""
    if not is_configured():
        raise LLMUnavailable("GEMINI_API_KEY is not set in .env")
    try:
        with httpx.Client(timeout=TIMEOUT_S, transport=transport) as client:
            return _gemini(messages, client)
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        raise LLMUnavailable(f"the language model could not be reached ({type(exc).__name__})") from exc
