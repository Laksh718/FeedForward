"""NLG back end of the copilot: turns the context JSON into words. One language model call per answer.

Flow: question -> NLU (rules) -> plain Python builds the context JSON -> ONE call to the language model writes the
explanation -> a check that every figure in the answer comes from the context -> answer.
If there is no key, no internet or the answer quotes a figure that is not in the context, the deterministic
template answer is used instead. Nothing here changes a quantity, approves a plan or runs anything the
language model asked for: the language model only receives text and returns text.
"""

import re
from datetime import date as Date
from functools import lru_cache

import pandas as pd

from feedforward import config as C
from feedforward.copilot import llm
from feedforward.copilot.context_builder import MESSAGES, build_context
from feedforward.copilot.nlu import Understanding, resolve_day, understand
from feedforward.copilot.prompts import build_v2
from feedforward.copilot.templates import template_answer
from feedforward.data.preprocess import dish_catalogue
from feedforward.models.forecast_service import ForecastService, Overrides

NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
SMALL = 10  # numbers below this (counts, "1 day in 10") are not checked


def _numbers(text: str) -> set[float]:
    out = set()
    for m in NUMBER.findall(text):
        try:
            out.add(float(m.replace(",", "")))
        except ValueError:
            continue
    return out


def _context_numbers(node) -> set[float]:
    """Every number that appears in the context, as a value or inside a sentence."""
    if isinstance(node, bool) or node is None:
        return set()
    if isinstance(node, (int, float)):
        return {abs(float(node)), round(abs(float(node)))}
    if isinstance(node, str):
        return _numbers(node)
    if isinstance(node, dict):
        return set().union(*(_context_numbers(v) for v in node.values())) if node else set()
    return set().union(*(_context_numbers(v) for v in node)) if node else set()


def ungrounded_numbers(answer: str, context: dict) -> list[float]:
    """Figures in the answer that are not in the context (numbers under 10 are ignored)."""
    allowed = _context_numbers(context)
    return sorted(x for x in _numbers(answer) if x >= SMALL and x not in allowed and round(x) not in allowed)


@lru_cache(maxsize=1)
def _dish_keys() -> dict[str, str]:
    return dish_catalogue(pd.read_parquet(C.PROCESSED_DIR / "dishes.parquet"))


def _result(answer: str, source: str, u: Understanding, ctx: dict | None, reason: str = "") -> dict:
    if u.extra_questions:
        answer += "\n(I answered your first question. Please ask the next one separately.)"
    return {"answer": answer, "source": source, "intent": u.intent, "fallback_reason": reason,
            "entities": u.entities, "context": ctx}


def answer_question(question: str, svc: ForecastService, page_date: Date, page_slot: str, scope: str,
                    page_overrides: Overrides, today: Date, use_llm: bool = True, transport=None) -> dict:
    """Answer one question. Returns the text, where it came from (llm, template or rules) and the context used."""
    u = understand(question, _dish_keys())
    first, last = Date.fromisoformat(C.HISTORY_START), Date.fromisoformat(C.FORECAST_LAST_DAY)
    if u.intent != "out_of_scope" and not first <= resolve_day(u, page_date, today) <= last:
        u.intent, u.reason = "out_of_scope", "off_topic"
        return _result(f"I only have calendar information from {first} to {last}. Ask about a day in that period.", "rules", u, None)
    ctx = build_context(u, svc, page_date, page_slot, scope, page_overrides, today)
    if u.intent == "out_of_scope":
        return _result(MESSAGES[u.reason], "rules", u, ctx)
    fallback = template_answer(ctx)
    if not use_llm:
        return _result(fallback, "template", u, ctx, "language model switched off")
    try:
        text = llm.complete(build_v2(question, ctx), transport)
    except llm.LLMUnavailable as exc:
        return _result(fallback, "template", u, ctx, str(exc))
    bad = ungrounded_numbers(text, ctx)
    if bad:
        return _result(fallback, "template", u, ctx, f"the model quoted figures that are not in the data: {bad[:4]}")
    return _result(text, "llm", u, ctx)
