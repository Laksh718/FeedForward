"""Seven day view: forecast totals for the next week and the actual demand of the last 7 days that have actuals."""

from datetime import date as Date
from datetime import timedelta
from functools import lru_cache

import pandas as pd

from feedforward.data.features import full_calendar
from feedforward.models.forecast_service import ForecastService

TOTAL_KEYS = ("p10", "p50", "p90", "recommended", "usual_plan")


@lru_cache(maxsize=1)
def _calendar_flags() -> pd.DataFrame:
    """Exam and holiday flags by date, for shading the week chart."""
    cal = full_calendar()
    return cal.set_index("date")[["university_exam_any", "formative_test_any", "tn_public_holiday"]]


def week_response(svc: ForecastService, start: Date, slot: str, scope: str, dish_id: str | None) -> dict:
    """Seven forecast days from `start`, and the last seven days with recorded demand before `start`."""
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
                     "expected_attendance": plan["expected_attendance"], "facts": plan.get("day_facts", {})})
    hist = svc.history
    before = hist.loc[(hist["meal_slot"] == slot) & (hist["date"] < pd.Timestamp(start)), "date"]
    mask = (hist["meal_slot"] == slot) & hist["date"].isin(sorted(before.unique())[-7:])   # days after the history ends have no actuals
    if dish_id:
        mask &= hist["dish_id"] == dish_id
    elif scope == "core":
        mask &= hist["dish_id"].isin(svc.dishes.loc[svc.dishes["forecast_priority"] == "core", "dish_id"])
    actual = (hist[mask].assign(demand=lambda d: d["consumed_qty"] + d["unmet_qty"]).groupby("date")["demand"].sum())
    past = [{"date": str(k.date()), "weekday": k.strftime("%a"), "actual": int(v)} for k, v in actual.items()]
    return {"meal_slot": slot, "scope": "dish" if dish_id else scope, "dish_id": dish_id, "start": str(start),
            "days": days, "past": past}
