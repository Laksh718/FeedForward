"""Builds the context JSON for a question: every number the answer may use, computed by plain Python.

The intent from nlu.py decides what is computed. The language model only receives this JSON and writes
words around it; it never runs anything and never chooses what is run.
"""

import json
from datetime import date as Date
from datetime import timedelta

from feedforward import config as C
from feedforward.copilot.nlu import Understanding, resolve_day
from feedforward.models.forecast_service import ForecastService, Overrides
from feedforward.models.week_view import week_response

WIDE_RANGE_PCT = 30   # a range wider than this share of the most likely amount counts as wide
TOTAL_KEYS = ("p10", "p50", "p90", "recommended", "usual_plan")
USUAL_PLAN_RULE = ("average of the same dish, meal and weekday over the last two weeks, plus "
                   f"{round(C.USUAL_PLAN_BUFFER * 100)} percent")
RISK_RULE = ("high when the usual plan is above the top of the likely range, medium when it is more than 10 percent "
             "above the most likely amount, otherwise low (a first version that a surplus detector will replace)")
DEFINITIONS = {
    "low_end": "about 1 day in 10 demand is expected to be below this",
    "most_likely": "the middle outcome: half of similar days are expected to be below it, half above",
    "high_end": "about 1 day in 10 demand is expected to be above this",
    "recommended": "the quantity to cook: it covers about 3 days in 4, so the line rarely runs dry",
    "usual_plan": USUAL_PLAN_RULE,
}
MESSAGES = {
    "action": "I only explain the numbers. To change or approve a plan, use the Change quantities and Approve buttons yourself.",
    "unclear_change": ("I can try a change in attendance (for example 15 percent more), in the weather (rain, a hot day), "
                       "or an exam week, festival or holiday. Ask in one of those ways, or use the what if controls."),
    "off_topic": ("I can explain this forecast: a dish against the usual plan, the likely range, a what if, the week, "
                  "or surplus risk."),
    "greeting": ("Hello! I explain the forecast on this page. Try: \"What should we cook for lunch?\", \"How much rice should "
                 "we make?\", \"Explain the range\", \"What if it rains?\" or \"Summarise the week\"."),
}


def _rows(plan: dict, scope: str) -> list[dict]:
    return [d for d in plan["dishes"] if d["is_core"]] if scope == "core" else plan["dishes"]


def _totals(rows: list[dict]) -> dict:
    t = {k: sum(r[k] for r in rows) for k in TOTAL_KEYS}
    t["range_width"] = t["p90"] - t["p10"]
    t["range_width_pct_of_most_likely"] = round(100 * t["range_width"] / t["p50"]) if t["p50"] else None
    return t


def _dish(r: dict) -> dict:
    width = r["p90"] - r["p10"]
    pct = round(100 * width / r["p50"]) if r["p50"] else None
    return {"name": r["dish_name"], "low_end": r["p10"], "most_likely": r["p50"], "high_end": r["p90"],
            "recommended": r["recommended"], "usual_plan": r["usual_plan"], "surplus_risk": r["surplus_risk"],
            "usual_plan_minus_most_likely": r["usual_plan"] - r["p50"] if r["usual_plan"] else None,
            "recommended_minus_usual_plan": r["recommended"] - r["usual_plan"] if r["usual_plan"] else None,
            "demand_last_week": r["last_week_demand"], "demand_two_weeks_ago": r["two_weeks_ago_demand"],
            "range_width": width, "range_width_pct_of_most_likely": pct,
            "range_is_wide": bool(pct is not None and pct > WIDE_RANGE_PCT),
            "limited_stock_dish": r["special_limited"], "has_history": r["has_history"]}


def _calibration() -> dict | None:
    """How often the real outcome fell inside the likely range in the held out checks (from reports/metrics.json)."""
    try:
        m = json.loads((C.REPORTS_DIR / "metrics.json").read_text(encoding="utf-8"))
        val, test = (m[k]["core_regular"]["cvae_calibrated"]["coverage_10_90"] for k in ("val", "test"))
        return {"percent_of_days_inside_range_validation": round(100 * val), "percent_of_days_inside_range_test": round(100 * test),
                "note": "the history is simulated, so these shares describe the simulation"}
    except (OSError, KeyError, ValueError):
        return None


def _caveats(plan: dict) -> list[str]:
    out = list(plan["notes"][:-1])   # the last note is the generic "history is simulated" line, stated separately
    if plan["day_facts"] and plan["day_facts"]["weather_is_assumed"]:
        out.append("The weather for this date is last year's monthly average, not a forecast.")
    return out


def _change_description(u: Understanding) -> tuple[str, Overrides]:
    """Words and the Overrides for the change a what if question asks about."""
    parts, ov = [], {}
    if u.pct is not None:
        ov["attendance_change_pct"] = u.pct
        parts.append(f"attendance {'up' if u.pct >= 0 else 'down'} {abs(u.pct):g} percent")
    if u.weather_type:
        ov["weather_type"] = u.weather_type
        parts.append("dry weather" if u.weather_type == "Dry" else f"weather: {u.weather_type.lower()}")
    if u.temp_max_c:
        ov["temp_max_c"] = u.temp_max_c
        parts.append(f"a hot day (maximum {u.temp_max_c:g} C, an assumed value)")
    for flag, label in (("exam_week", "an exam week"), ("festival", "a festival"), ("special_day", "a holiday or special day")):
        if flag in u.flags:
            ov[flag] = u.flags[flag]
            parts.append(label if u.flags[flag] else f"no {label.split(' ', 1)[1]}")
    return " and ".join(parts), Overrides(**ov)


def build_context(u: Understanding, svc: ForecastService, page_date: Date, page_slot: str, scope: str,
                  page_overrides: Overrides, today: Date) -> dict:
    """The context for one question. For out of scope questions it only carries the reason and a fixed message."""
    ctx: dict = {"intent": u.intent, "question": u.question, "answers_first_question_only": u.extra_questions > 0}
    if u.intent == "out_of_scope":
        ctx.update(reason=u.reason, message=MESSAGES[u.reason])
        return ctx
    slot, day = u.slot or page_slot, resolve_day(u, page_date, today)
    ctx.update(date=str(day), weekday=day.strftime("%A"), meal_slot=slot, scope=scope, usual_plan_rule=USUAL_PLAN_RULE)
    if u.intent.startswith("whatif"):
        text, ov = _change_description(u)
        base, changed = svc.forecast(day, slot), svc.forecast(day, slot, overrides=ov)
        b, c = _totals(_rows(base, scope)), _totals(_rows(changed, scope))
        diffs = sorted(({"name": x["dish_name"], "recommended_before": y["recommended"], "recommended_after": x["recommended"],
                         "change": x["recommended"] - y["recommended"]}
                        for x, y in zip(_rows(changed, scope), _rows(base, scope), strict=True)), key=lambda d: -abs(d["change"]))
        ctx.update(change=text, before=b, after=c, expected_attendance_before=base["expected_attendance"],
                   expected_attendance_after=changed["expected_attendance"],
                   change_in_recommended=c["recommended"] - b["recommended"],
                   change_in_most_likely=c["p50"] - b["p50"],
                   change_in_recommended_pct=round(100 * (c["recommended"] - b["recommended"]) / b["recommended"], 1) if b["recommended"] else None,
                   biggest_dish_changes=diffs[:3], day_facts=changed["day_facts"], caveats=_caveats(changed))
        return ctx
    plan = svc.forecast(day, slot, overrides=page_overrides)
    rows = _rows(plan, scope)
    ctx.update(day_facts=plan["day_facts"], slot_totals=_totals(rows), caveats=_caveats(plan),
               page_has_what_if=bool(plan["overrides_applied"]))
    if u.intent == "explain_dish":
        match = [r for r in plan["dishes"] if r["dish_id"] in u.dish_ids]
        ctx["dish"] = _dish(match[0]) if match else None
        if u.dish_ids and not match:
            names = svc.dishes.set_index("dish_id")["dish_name"]
            ctx["missing"] = [f"{names.get(u.dish_ids[0], 'That dish')} is not on the {slot} menu on {ctx['weekday']}."]
        ctx["other_dishes_named"] = len(u.dish_ids) - 1 if len(u.dish_ids) > 1 else 0
    elif u.intent == "explain_range":
        top = sorted(rows, key=lambda r: -r["recommended"])[:3]
        ctx.update(definitions=DEFINITIONS, example_dishes=[_dish(r) for r in top], calibration=_calibration())
    elif u.intent == "summarise_surplus_risk":
        ctx.update(risk_rule=RISK_RULE, risk_counts={lvl: sum(r["surplus_risk"] == lvl for r in rows) for lvl in ("high", "medium", "low")},
                   dishes_at_risk=[_dish(r) for r in rows if r["surplus_risk"] != "low"][:6])
        if "week" in u.question.lower():
            ctx["week_risk"] = _week_risk(svc, today, slot, scope)
    elif u.intent == "explain_week":
        ctx.update(_week_context(svc, today, slot, scope, u))
    return ctx


def _week_risk(svc: ForecastService, today: Date, slot: str, scope: str) -> list[dict]:
    out = []
    for i in range(1, 8):
        d = today + timedelta(days=i)
        rows = _rows(svc.forecast(d, slot), scope)
        out.append({"weekday": d.strftime("%A"), "date": str(d), **{lvl: sum(r["surplus_risk"] == lvl for r in rows) for lvl in ("high", "medium", "low")}})
    return out


def _week_context(svc: ForecastService, today: Date, slot: str, scope: str, u: Understanding) -> dict:
    """Seven days from tomorrow: totals, flags, the days asked about and the previous week's actual demand."""
    week = week_response(svc, today + timedelta(days=1), slot, scope, None)
    days = [{"weekday": Date.fromisoformat(d["date"]).strftime("%A"), "date": d["date"], "most_likely": d["p50"], "low_end": d["p10"], "high_end": d["p90"],
             "recommended": d["recommended"], "usual_plan": d["usual_plan"], "exam_week": d["exam_week"], "holiday": d["holiday"],
             "expected_attendance": d["expected_attendance"],
             "attendance_last_week": (d["facts"] or {}).get("attendance_last_week")} for d in week["days"]]
    wanted = {w.lower() for w in u.day_words}
    focus = [d for d in days if d["weekday"].lower() in wanted]
    for d in focus:
        i = days.index(d)
        d["change_from_previous_day"] = d["most_likely"] - days[i - 1]["most_likely"] if i else None
    past = {Date.fromisoformat(p["date"]).strftime("%A").lower(): p["actual"] for p in week["past"]}
    for d in focus:
        d["same_weekday_last_week_actual"] = past.get(d["weekday"].lower())
    top, low = max(days, key=lambda d: d["most_likely"]), min(days, key=lambda d: d["most_likely"])
    return {"week_days": days, "focus_days": focus, "highest_day": top["weekday"], "lowest_day": low["weekday"],
            "past_week_actual_demand": week["past"], "totals_note": "totals add the dishes shown (" + ("main dishes" if scope == "core" else "all dishes") + ")"}
