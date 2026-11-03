"""One call to a hosted language model over HTTP. It only turns figures into words.

Google Gemini is used when GEMINI_API_KEY is set; otherwise Groq when GROQ_API_KEY is set. Keys are read from .env
(or the host's environment) and are never printed or logged. If there is no key, no internet or the service fails,
LLMUnavailable is raised and the caller uses the template answer instead.
"""

import os

import httpx
from dotenv import load_dotenv

from feedforward import config as C

load_dotenv(C.PROJECT_ROOT / ".env")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_DEFAULT_MODEL = "gemini-3.5-flash-lite"  # fast (about 2 to 5 s here) and enough for a short rewording; change with GEMINI_MODEL
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"   # change with GROQ_MODEL; check the name in your Groq console
TEMPERATURE = 0.2                           # low, so the same question gives nearly the same answer
MAX_TOKENS = 500                            # answers are short by design
GEMINI_THINKING_TOKENS = 2048               # newer Gemini models think first, and that counts against the output limit
TIMEOUT_S = 20.0

# Kept for callers and scripts that used the Groq only names.
DEFAULT_MODEL = GROQ_DEFAULT_MODEL


class LLMUnavailable(RuntimeError):
    """No key, no network or the service refused the call."""


def _key(name: str) -> str:
    return os.getenv(name, "").strip()


def provider() -> str | None:
    """Which service a call would use: "gemini", "groq" or None when no key is set."""
    if _key("GEMINI_API_KEY"):
        return "gemini"
    if _key("GROQ_API_KEY"):
        return "groq"
    return None


def is_configured() -> bool:
    """True when a key is present (it may still fail at call time)."""
    return provider() is not None


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


def complete(messages: list[dict], transport: httpx.BaseTransport | None = None) -> str:
    """Send the messages once and return the reply text. `transport` is for tests only."""
    which = provider()
    if which is None:
        raise LLMUnavailable("neither GEMINI_API_KEY nor GROQ_API_KEY is set in .env")
    try:
        with httpx.Client(timeout=TIMEOUT_S, transport=transport) as client:
            if which == "gemini":
                model = os.getenv("GEMINI_MODEL", "").strip() or GEMINI_DEFAULT_MODEL
                r = client.post(GEMINI_URL.format(model=model), json=_gemini_body(messages, model),
                                headers={"x-goog-api-key": _key("GEMINI_API_KEY")})
                r.raise_for_status()
                return _gemini_text(r.json())
            body = {"model": os.getenv("GROQ_MODEL", "").strip() or GROQ_DEFAULT_MODEL, "messages": messages,
                    "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS, "reasoning_effort": "low"}
            r = client.post(GROQ_URL, json=body, headers={"Authorization": f"Bearer {_key('GROQ_API_KEY')}"})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        raise LLMUnavailable(f"the language model could not be reached ({type(exc).__name__})") from exc
