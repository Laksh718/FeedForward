"""Builds API responses from the forecast service. Plain Python; no language model is involved."""

from datetime import date as Date
from datetime import timedelta
from functools import lru_cache

import pandas as pd

from feedforward import config as C
from feedforward.admin.review_log import latest_review
from feedforward.data.features import full_calendar
from feedforward.models.forecast_service import ForecastService, Overrides

TOTAL_KEYS = ("p10", "p50", "p90", "recommended", "usual_plan")
DATA_SOURCE_CHIP = "Simulated history on a real menu, calendar and weather"


def today() -> Date:
    """The project's today (config, or FEEDFORWARD_TODAY in .env for demos)."""
    import os

    return Date.fromisoformat(os.getenv("FEEDFORWARD_TODAY", C.TODAY))


def n(value: float) -> str:
    """Whole number with thousands separator, for sentences."""
    return f"{int(round(value)):,}"


def headline(slot: str, rec: int, usual: int, p50: int) -> dict:
    """Kitchen manager sentences built from the numbers (the dashboard shows them as given)."""
    diff = usual - rec
    if usual <= 0:
        compare = ". There is no usual plan to compare with yet"
    elif abs(diff) < max(5, 0.005 * usual):
        compare = ", the same as the usual plan"
    else:
        compare = f", {n(abs(diff))} {'fewer' if diff > 0 else 'more'} than the usual plan"
    margin = rec - p50
    support = (f"Most likely demand is {n(p50)} portions. The extra {n(margin)} is a safety margin so the line "
               "does not run dry." if margin > 0 else f"Most likely demand is {n(p50)} portions.")
    return {"headline": f"Cook {n(rec)} portions for {slot}{compare}.", "supporting": support}


def scoped(plan: dict, scope: str) -> dict:
    """Keep core dishes only (default) or all dishes, and recompute totals for what is kept."""
    dishes = [d for d in plan["dishes"] if d["is_core"]] if scope == "core" else plan["dishes"]
    out = dict(plan, dishes=dishes, scope=scope, dishes_hidden=len(plan["dishes"]) - len(dishes))
    out["totals"] = {k: sum(d[k] for d in dishes) for k in TOTAL_KEYS}
    return out


def plan_response(svc: ForecastService, day: Date, slot: str, overrides: Overrides | None, scope: str) -> dict:
    """Plan for one date and slot with headline sentences and the review status."""
    plan = scoped(svc.forecast(day, slot, overrides=overrides), scope)
    t = plan["totals"]
    plan.update(headline(slot, t["recommended"], t["usual_plan"], t["p50"]))
    plan["weekday"] = pd.Timestamp(day).day_name()
    plan["review"] = latest_review(plan["date"], slot)
    plan["risk_counts"] = {lvl: sum(d["surplus_risk"] == lvl for d in plan["dishes"]) for lvl in ("high", "medium", "low")}
    return plan


@lru_cache(maxsize=1)
def _calendar_flags() -> pd.DataFrame:
    """Exam and holiday flags by date, for shading the week chart."""
    cal = full_calendar()
    return cal.set_index("date")[["university_exam_any", "formative_test_any", "tn_public_holiday"]]


def week_response(svc: ForecastService, start: Date, slot: str, scope: str, dish_id: str | None) -> dict:
    """Seven forecast days from `start`, and the seven days before it as actual demand."""
    days = []
    flags = _calendar_flags()
    for i in range(7):
        d = start + timedelta(days=i)
        plan = svc.forecast(d, slot, dish_ids=[dish_id] if dish_id else None)
        rows = [r for r in plan["dishes"] if r["is_core"] or dish_id or scope == "all"]
        f = flags.loc[pd.Timestamp(d)] if pd.Timestamp(d) in flags.index else None
        days.append({"date": str(d), "weekday": d.strftime("%a"),
                     **{k: sum(r[k] for r in rows) for k in TOTAL_KEYS},
                     "exam_week": bool(f is not None and f["university_exam_any"]),
                     "holiday": bool(f is not None and f["tn_public_holiday"]),
                     "expected_attendance": plan["expected_attendance"]})
    hist = svc.history
    mask = (hist["meal_slot"] == slot) & (hist["date"] >= pd.Timestamp(start - timedelta(days=7))) & (hist["date"] < pd.Timestamp(start))
    if dish_id:
        mask &= hist["dish_id"] == dish_id
    elif scope == "core":
        mask &= hist["dish_id"].isin(svc.dishes.loc[svc.dishes["forecast_priority"] == "core", "dish_id"])
    actual = (hist[mask].assign(demand=lambda d: d["consumed_qty"] + d["unmet_qty"]).groupby("date")["demand"].sum())
    past = [{"date": str(k.date()), "weekday": k.strftime("%a"), "actual": int(v)} for k, v in actual.items()]
    return {"meal_slot": slot, "scope": "dish" if dish_id else scope, "dish_id": dish_id, "start": str(start),
            "days": days, "past": past}
