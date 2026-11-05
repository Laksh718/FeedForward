"""Copilot: NLU intents and entities, context numbers, template answers, grounding check, language model fallback."""

import json
import re
from datetime import date, timedelta
from pathlib import Path

import httpx
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from api.main import create_app
from feedforward import config as C
from feedforward.copilot import llm
from feedforward.copilot.context_builder import build_context
from feedforward.copilot.explain import answer_question, ungrounded_numbers
from feedforward.copilot.nlu import resolve_day, understand
from feedforward.copilot.prompts import build_v1, build_v2
from feedforward.copilot.templates import template_answer
from feedforward.data.preprocess import dish_catalogue
from feedforward.models.forecast_service import ForecastService, Overrides

pytestmark = pytest.mark.skipif(not (C.MODELS_DIR / "final" / "cvae.pt").exists(), reason="final model missing")
TODAY = date(2026, 10, 6)
INTENT_CASES = [
    ("Why is veg briyani below the usual plan?", "explain_dish"),
    ("Why is Chappathi above the usual plan?", "explain_dish"),
    ("Why is the usual plan higher?", "explain_dish"),
    ("What if attendance rises 15%?", "whatif_attendance"),
    ("What if attendance drops by 10 percent on Monday?", "whatif_attendance"),
    ("What if it rains heavily?", "whatif_weather"),
    ("What if it does not rain tomorrow?", "whatif_weather"),
    ("What happens if it is hot on Friday dinner?", "whatif_weather"),
    ("What does an exam week do to demand?", "whatif_special_day"),
    ("What if there is a festival?", "whatif_special_day"),
    ("Explain the P10 to P90 range to someone who is not technical.", "explain_range"),
    ("How sure are you about this forecast?", "explain_range"),
    ("Summarise the week's surplus risk.", "summarise_surplus_risk"),
    ("Which dishes are at risk of leftovers?", "summarise_surplus_risk"),
    ("Why is Tuesday so high?", "explain_week"),
    ("Explain the Monday and Tuesday rise", "explain_week"),
    ("Approve the plan", "out_of_scope"),
    ("Change the quantity of rice to 500", "out_of_scope"),
    ("Tell me a joke", "out_of_scope"),
    ("What if more students come?", "out_of_scope"),
    ("Is the milk powder stock enough?", "out_of_scope"),
]


@pytest.fixture(scope="module")
def keys():
    return dish_catalogue(pd.read_parquet(C.PROCESSED_DIR / "dishes.parquet"))


@pytest.fixture(scope="module")
def svc():
    return ForecastService()


@pytest.fixture(autouse=True)
def no_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "")


@pytest.mark.parametrize(("question", "intent"), INTENT_CASES)
def test_intents(keys, question, intent):
    assert understand(question, keys).intent == intent


def test_entities_and_parameters(keys):
    u = understand("What if attendance drops by 10 percent on Monday dinner?", keys)
    assert u.pct == -10 and u.slot == "dinner" and u.day_words == ["monday"]
    assert understand("What if attendance rises 15%?", keys).pct == 15
    assert understand("Why is veg briyani below the usual plan?", keys).dish_ids == ["D090"]
    assert understand("Why is veg biriyani low", keys).dish_ids == ["D090"]      # misspelling still found


def test_negation_is_kept(keys):
    assert understand("What if it does not rain tomorrow?", keys).weather_type == "Dry"
    assert understand("What if there is no exam week?", keys).flags == {"exam_week": False}
    assert understand("What if it rains heavily?", keys).weather_type == "Heavy Rain"


def test_only_first_question_is_answered(keys):
    u = understand("Why is chappathi high? What about dinner?", keys)
    assert u.intent == "explain_dish" and u.extra_questions == 1


def test_resolve_day(keys):
    u = understand("Why is Tuesday so high?", keys)
    assert resolve_day(u, TODAY + timedelta(days=1), TODAY) == date(2026, 10, 13)   # next Tuesday after 2026-10-06
    assert resolve_day(understand("what if it rains tomorrow", keys), TODAY, TODAY) == date(2026, 10, 7)


@pytest.mark.parametrize(("question", "intent"), [q for q in INTENT_CASES if q[1] != "out_of_scope"])
def test_context_and_template_use_only_context_figures(keys, svc, question, intent):
    u = understand(question, keys)
    ctx = build_context(u, svc, TODAY + timedelta(days=1), "lunch", "core", Overrides(), TODAY)
    text = template_answer(ctx)
    assert ctx["intent"] == intent
    assert text.startswith("Short answer:") and "Key drivers:" in text and "One caution:" in text
    assert ungrounded_numbers(text, ctx) == []


def test_whatif_context_is_consistent(keys, svc):
    ctx = build_context(understand("What if attendance rises 15%?", keys), svc, TODAY + timedelta(days=1), "lunch", "core",
                        Overrides(), TODAY)
    assert ctx["change_in_recommended"] == ctx["after"]["recommended"] - ctx["before"]["recommended"] > 0
    assert ctx["expected_attendance_after"] > ctx["expected_attendance_before"]


def test_dish_not_on_menu_is_reported(keys, svc):
    ctx = build_context(understand("Why is veg briyani below the usual plan?", keys), svc, TODAY + timedelta(days=1), "lunch",
                        "core", Overrides(), TODAY)
    assert ctx["dish"] is None and "not on the lunch menu" in ctx["missing"][0]
    assert "Veg Briyani" in template_answer(ctx)


def test_grounding_check():
    ctx = {"a": 12250, "b": [1, 2, {"c": "range 8,921 to 13,457"}], "d": 3.5}
    assert ungrounded_numbers("Cook 12,250 portions, range 8,921 to 13,457, about 3 days in 4.", ctx) == []
    assert ungrounded_numbers("Cook 99,999 portions.", ctx) == [99999.0]


def _model(text: str | None = None, fail: bool = False, seen: list | None = None):
    """A fake Gemini endpoint that answers with `text`."""
    def handler(request: httpx.Request) -> httpx.Response:
        if seen is not None:
            seen.append(request)
        if fail:
            raise httpx.ConnectError("offline")
        return httpx.Response(200, json={"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}]})
    return httpx.MockTransport(handler)


def _ask(svc, transport, monkeypatch, key="test-key", q="Why is Chappathi above the usual plan?"):
    monkeypatch.setenv("GEMINI_API_KEY", key)
    return answer_question(q, svc, TODAY + timedelta(days=1), "lunch", "core", Overrides(), TODAY, transport=transport)


def test_good_model_answer_is_used(svc, monkeypatch):
    good = ("Short answer: The usual plan is 3,199 and we suggest cooking 3,430.\nKey drivers:\n- Last week 2,793 were wanted.\n"
            "One caution: The likely range is 2,621 to 3,713.")
    seen = []
    r = _ask(svc, _model(good, seen=seen), monkeypatch)
    assert r["source"] == "llm" and r["answer"] == good
    req = seen[0]
    assert "gemini" in req.url.path and req.headers["x-goog-api-key"] == "test-key" and "key=" not in str(req.url)
    body = json.loads(req.content)
    assert "Use only the numbers in the CONTEXT JSON" in body["systemInstruction"]["parts"][0]["text"]
    assert [c["role"] for c in body["contents"]] == ["user", "model", "user", "model", "user"]
    assert body["generationConfig"]["temperature"] == llm.TEMPERATURE


def test_gemini_is_the_only_model_and_odd_replies_fail(monkeypatch):
    monkeypatch.setenv("GROQ_API_KEY", "q")       # a leftover Groq key is ignored
    assert not llm.is_configured()
    with pytest.raises(llm.LLMUnavailable):
        llm.complete([{"role": "user", "content": "hi"}])
    monkeypatch.setenv("GEMINI_API_KEY", "g")
    assert llm.is_configured()
    blocked = httpx.MockTransport(lambda r: httpx.Response(200, json={"candidates": [], "promptFeedback": {"blockReason": "SAFETY"}}))
    with pytest.raises(llm.LLMUnavailable):
        llm.complete([{"role": "user", "content": "hi"}], blocked)
    thought = httpx.MockTransport(lambda r: httpx.Response(200, json={"candidates": [{"content": {"parts": [
        {"text": "thinking...", "thought": True}, {"text": "The answer."}]}}]}))
    assert llm.complete([{"role": "user", "content": "hi"}], thought) == "The answer."


def test_invented_figures_fall_back_to_template(svc, monkeypatch):
    r = _ask(svc, _model("Short answer: Cook 7,777 portions.\nKey drivers:\n- x\nOne caution: y"), monkeypatch)
    assert r["source"] == "template" and "not in the data" in r["fallback_reason"] and "7,777" not in r["answer"]


def test_no_key_or_no_network_falls_back_to_template(svc, monkeypatch):
    assert _ask(svc, None, monkeypatch, key="")["source"] == "template"
    r = _ask(svc, _model(fail=True), monkeypatch)
    assert r["source"] == "template" and "could not be reached" in r["fallback_reason"]
    assert llm.is_configured() is True


def test_out_of_scope_never_calls_the_model(svc, monkeypatch):
    def boom(request):
        raise AssertionError("the model must not be called")
    r = _ask(svc, httpx.MockTransport(boom), monkeypatch, q="Approve the plan")
    assert r["source"] == "rules" and "Approve buttons yourself" in r["answer"]


def test_prompt_versions():
    v1 = build_v1("Why is rice high?")
    assert len(v1) == 1 and "CONTEXT" not in v1[0]["content"]
    v2 = build_v2("Why is rice high?", {"intent": "explain_dish", "x": 5})
    assert [m["role"] for m in v2] == ["system", "user", "assistant", "user", "assistant", "user"]   # role, two examples, question
    assert "Use only the numbers in the CONTEXT JSON" in v2[0]["content"] and '"x": 5' in v2[-1]["content"]
    assert "Short answer:" in v2[0]["content"] and "One caution:" in v2[0]["content"]


def test_chat_endpoint_without_key():
    client = TestClient(create_app())
    r = client.post("/api/chat", json={"question": "What if attendance rises 15%?", "meal_slot": "lunch", "date": "2026-10-07"})
    body = r.json()
    assert r.status_code == 200 and body["source"] == "template" and body["intent"] == "whatif_attendance"
    assert body["answer"].startswith("Short answer:") and body["context"]["change"].startswith("attendance up 15")
    assert client.post("/api/chat", json={"question": ""}).status_code == 422


def test_no_forbidden_words_anywhere_in_the_project():
    forbidden = re.compile(r"agent|autonomous|orchestrat|tool[ _-]?call|function[ _-]?call|multi[ _-]?step plan|workflow automation", re.I)
    root, bad = C.PROJECT_ROOT, []
    for folder in ("src", "api", "app", "docs", "tests", "scripts"):
        for f in (root / folder).rglob("*"):
            skip = f.name in ("test_copilot.py", "code_bundle_preprocessing.md") or "__pycache__" in f.parts
            if f.is_file() and f.suffix in {".py", ".md", ".html", ".js", ".css", ".mjs", ".ps1"} and not skip:
                bad += [f"{f.relative_to(root)}: {m.group(0)}" for m in forbidden.finditer(f.read_text(encoding="utf-8", errors="ignore"))]
    for name in ("README.md", "pyproject.toml", ".env.example"):
        bad += [f"{name}: {m.group(0)}" for m in forbidden.finditer(Path(root / name).read_text(encoding="utf-8"))]
    assert not bad, bad





def test_quoting_the_wide_range_rule_is_not_an_invented_figure():
    ctx = {"totals": {"most_likely": 12469, "range_width_pct_of_most_likely": 41}}
    assert ungrounded_numbers("The range is over 30 percent of the most likely 12,469, so it is uncertain.", ctx) == []
    assert ungrounded_numbers("Cook 7,777 because the range is over 30 percent.", ctx) == [7777.0]


@pytest.mark.parametrize("question", ["hi", "Hello!", "thanks", "good morning"])
def test_greetings_get_a_hello_with_examples(svc, question):
    r = answer_question(question, svc, TODAY + timedelta(days=1), "lunch", "core", Overrides(), TODAY)
    assert r["source"] == "rules" and r["answer"].startswith("Hello!") and "What should we cook" in r["answer"]


@pytest.mark.parametrize("question", ["tell me what to plan", "What should we cook for lunch?", "what to plan for dinner",
                                      "give me the plan", "How many portions?"])
def test_planning_questions_explain_the_plan(keys, question):
    assert understand(question, keys).intent == "explain_dish"


def test_part_of_a_dish_name_finds_the_dish_on_the_menu(svc):
    r = answer_question("How much rice should I make?", svc, TODAY + timedelta(days=1), "lunch", "core", Overrides(), TODAY, use_llm=False)
    assert r["intent"] == "explain_dish" and r["context"]["dish"]["name"] == "Steamed Rice"


@pytest.mark.parametrize("question", ["Is the milk powder stock enough?", "Tell me a joke", "hi, can you approve it"])
def test_new_rules_keep_other_questions_out(keys, question):
    assert understand(question, keys).intent == "out_of_scope"


GOOD = ("Short answer: The usual plan is 3,199 and we suggest cooking 3,430.\nKey drivers:\n- Last week 2,793 were wanted.\n"
        "One caution: The likely range is 2,621 to 3,713.")
BAD = "Short answer: Cook 7,777 portions.\nKey drivers:\n- x\nOne caution: y"


def test_exactly_one_request_per_answer(svc, monkeypatch):
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    seen = []
    r = _ask(svc, _model(GOOD, seen=seen), monkeypatch)
    assert r["source"] == "llm" and len(seen) == 1
    assert "generativelanguage.googleapis.com" in str(seen[0].url) and llm.GEMINI_DEFAULT_MODEL in seen[0].url.path


def test_a_failed_request_is_not_retried_and_the_template_is_used(svc, monkeypatch):
    seen = []
    busy = httpx.MockTransport(lambda request: (seen.append(request), httpx.Response(503, json={}))[1])
    r = _ask(svc, busy, monkeypatch)
    assert len(seen) == 1 and r["source"] == "template" and "could not be reached" in r["fallback_reason"]


def test_a_bad_number_in_the_answer_is_rejected_after_one_request(svc, monkeypatch):
    seen = []
    r = _ask(svc, _model(BAD, seen=seen), monkeypatch)
    assert len(seen) == 1 and r["source"] == "template" and "7,777" not in r["answer"]
    assert r["answer"].startswith("Short answer:") and "not in the data" in r["fallback_reason"]
