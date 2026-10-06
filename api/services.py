"""Builds API responses from the forecast service. Plain Python; no language model is involved."""

from datetime import date as Date

import pandas as pd

from feedforward import config as C
from feedforward.admin.review_log import latest_review
from feedforward.models.forecast_service import ForecastService, Overrides
from feedforward.models.week_view import TOTAL_KEYS, week_response  # noqa: F401  (shared with the copilot)

DATA_SOURCE_CHIP = "Simulated history on a real menu, calendar and weather"


def today() -> Date:
    """The project's today (config, or FEEDFORWARD_TODAY in .env for demos)."""
    import os

    return Date.fromisoformat(os.getenv("FEEDFORWARD_TODAY") or C.TODAY)  # empty value means the default


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
