"""One call to a hosted language model over HTTP. It only turns figures into words.

Google Gemini is used when GEMINI_API_KEY is set; otherwise Groq when GROQ_API_KEY is set. Keys are read from .env
(or the host's environment) and are never printed or logged. If there is no key, no internet or the service fails,
LLMUnavailable is raised and the caller uses the template answer instead.

Gemini's speed swings with demand (the same model can answer in 2 seconds and then take 30), so a Gemini call tries
a short chain of models: each gets GEMINI_TIMEOUT_S, and a slow, overloaded, rate limited or unavailable model hands
over to the next one, within TOTAL_BUDGET_S overall.
"""

import os
import time

import httpx
from dotenv import load_dotenv

from feedforward import config as C

load_dotenv(C.PROJECT_ROOT / ".env")
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
GEMINI_DEFAULT_MODEL = "gemini-3.1-flash-lite"   # change with GEMINI_MODEL
GEMINI_DEFAULT_FALLBACKS = ("gemini-3.1-flash-lite", "gemini-3.5-flash-lite", "gemini-flash-lite-latest")   # GEMINI_FALLBACK_MODELS
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = "openai/gpt-oss-20b"   # change with GROQ_MODEL; check the name in your Groq console
TEMPERATURE = 0.2                           # low, so the same question gives nearly the same answer
MAX_TOKENS = 500                            # answers are short by design
GEMINI_THINKING_TOKENS = 2048               # newer Gemini models think first, and that counts against the output limit
TIMEOUT_S = 20.0                            # one Groq call
GEMINI_TIMEOUT_S = 8.0                      # one Gemini model (a free Lite model usually answers in 1 to 4 s) before the next
TOTAL_BUDGET_S = 26.0                       # all Gemini attempts together, so the copilot never hangs
RETRY_STATUS = {404, 408, 429, 500, 502, 503, 504}   # worth trying another model; 400, 401 and 403 are not

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


def gemini_models() -> list[str]:
    """GEMINI_MODEL first, then the fallbacks (GEMINI_FALLBACK_MODELS, comma separated), without repeats."""
    first = _key("GEMINI_MODEL") or GEMINI_DEFAULT_MODEL
    raw = os.getenv("GEMINI_FALLBACK_MODELS")
    rest = [m.strip() for m in raw.split(",")] if raw is not None else list(GEMINI_DEFAULT_FALLBACKS)
    out = []
    for m in [first, *rest]:
        if m and m not in out:
            out.append(m)
    return out


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
    key, started, last = _key("GEMINI_API_KEY"), time.monotonic(), "no model tried"
    for model in gemini_models():
        left = TOTAL_BUDGET_S - (time.monotonic() - started)
        if left < 2:
            break
        try:
            r = client.post(GEMINI_URL.format(model=model), json=_gemini_body(messages, model),
                            headers={"x-goog-api-key": key}, timeout=min(GEMINI_TIMEOUT_S, left))
        except httpx.TransportError as exc:          # timeout or network trouble: try the next model
            last = type(exc).__name__
            continue
        if r.status_code in RETRY_STATUS:
            last = f"HTTP {r.status_code}"
            continue
        r.raise_for_status()                          # a refused key or a bad request will not improve with another model
        try:
            return _gemini_text(r.json())
        except (KeyError, IndexError, TypeError, ValueError):   # blocked or empty reply: another model may still answer
            last = "empty or blocked reply"
    raise LLMUnavailable(f"the language model could not be reached ({last})")


def complete(messages: list[dict], transport: httpx.BaseTransport | None = None) -> str:
    """Send the messages and return the reply text. `transport` is for tests only."""
    which = provider()
    if which is None:
        raise LLMUnavailable("neither GEMINI_API_KEY nor GROQ_API_KEY is set in .env")
    try:
        with httpx.Client(timeout=TIMEOUT_S, transport=transport) as client:
            if which == "gemini":
                return _gemini(messages, client)
            body = {"model": _key("GROQ_MODEL") or GROQ_DEFAULT_MODEL, "messages": messages,
                    "temperature": TEMPERATURE, "max_tokens": MAX_TOKENS, "reasoning_effort": "low"}
            r = client.post(GROQ_URL, json=body, headers={"Authorization": f"Bearer {_key('GROQ_API_KEY')}"})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]["content"].strip()
    except (httpx.HTTPError, KeyError, IndexError, ValueError, TypeError) as exc:
        raise LLMUnavailable(f"the language model could not be reached ({type(exc).__name__})") from exc
