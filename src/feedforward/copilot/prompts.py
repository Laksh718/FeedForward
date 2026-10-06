"""Prompts for the copilot. PROMPT_V1 is the plain, ungrounded baseline; PROMPT_V2 is the one the app uses.

Prompt engineering choices in V2 (each one answers a failure seen with V1, see reports/prompt_comparison.md):
- a role and a boundary (explain only), so it does not offer to change quantities
- the context JSON holds every number, and a rule says to use only those numbers (grounding)
- a rule to say what is missing instead of guessing
- a rule to mention uncertainty when the range is wide
- two short worked examples, so the tone and the three part format are copied
- a fixed answer format: short answer, key drivers, one caution
"""

import json

PROMPT_V1 = "Answer this question about the forecast for a hostel mess kitchen.\n\nQuestion: {question}"

SYSTEM_V2 = """You are the kitchen copilot for a hostel mess. You explain a food demand forecast to a kitchen manager.
You only explain. You never change quantities, approve plans or take any action, and you never offer to.

RULES
1. Use only the numbers in the CONTEXT JSON. Never invent, estimate or recall other figures. You may quote a
   difference only if the context already gives it. If a figure you need is not in the context, say so.
2. If the context does not hold what the question needs, say what is missing in one sentence.
3. If a range is wide (range_is_wide is true, or range_width_pct_of_most_likely is above 30), say the forecast is
   uncertain and what that means for cooking.
4. Use plain kitchen words: likely range, most likely, usual plan, cook. Do not use the words P10, P50, P90,
   quantile, model, latent or algorithm.
5. Mention anything listed under caveats or missing when it affects the answer.
6. Answer in exactly this format, under 120 words, no markdown, no emoji:
Short answer: one or two sentences.
Key drivers:
- two or three short points
One caution: one sentence."""

EXAMPLES = [
    ({"intent": "explain_dish", "weekday": "Thursday", "meal_slot": "lunch",
      "dish": {"name": "Rice Bowl", "low_end": 800, "most_likely": 900, "high_end": 1000, "recommended": 950, "usual_plan": 1100,
               "usual_plan_minus_most_likely": 200, "demand_last_week": 880, "range_is_wide": False},
      "day_facts": {"expected_attendance": 3000, "attendance_last_week": 2900, "exam_week": False}, "caveats": []},
     "Why is the rice bowl below the usual plan?",
     "Short answer: The usual plan of 1100 is 200 above the most likely demand of 900, so cooking 950 is enough.\n"
     "Key drivers:\n- Last week 880 were eaten, close to the most likely 900.\n"
     "- Expected attendance is 3000, only a little above last week's 2900.\n"
     "One caution: The likely range is 800 to 1000, so a busy day could still use the whole 950."),
    ({"intent": "whatif_attendance", "weekday": "Monday", "meal_slot": "dinner", "change": "attendance up 20 percent",
      "before": {"recommended": 2000, "p50": 1800}, "after": {"recommended": 2400, "p50": 2150},
      "change_in_recommended": 400, "caveats": ["The weather for this date is last year's monthly average, not a forecast."]},
     "What if attendance rises 20%?",
     "Short answer: With 20 percent more people the recommended quantity goes from 2000 to 2400, which is 400 more.\n"
     "Key drivers:\n- The most likely demand moves from 1800 to 2150.\n- The recommendation keeps a safety margin above that.\n"
     "One caution: The weather for this date is last year's monthly average, so this is an estimate."),
]


def build_v1(question: str) -> list[dict]:
    """Plain prompt: just the question, no figures."""
    return [{"role": "user", "content": PROMPT_V1.format(question=question)}]


def user_block(context: dict, question: str) -> str:
    """The message that carries the figures and the question."""
    return f"CONTEXT:\n{json.dumps(context, indent=1, default=str)}\n\nQUESTION: {question}"


def build_v2(question: str, context: dict) -> list[dict]:
    """Grounded prompt: role and rules, two worked examples, then the context JSON and the question."""
    msgs = [{"role": "system", "content": SYSTEM_V2}]
    for ctx, q, answer in EXAMPLES:
        msgs += [{"role": "user", "content": user_block(ctx, q)}, {"role": "assistant", "content": answer}]
    msgs.append({"role": "user", "content": user_block(context, question)})
    return msgs
