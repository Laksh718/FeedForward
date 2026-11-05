"""Plans for the coming days, decisions on many plans at once, the dish by dish forecast of several days, and the
activity feed.

GET  /api/plans             every meal of the next days: totals, risk, the standing decision and whether it is logged
POST /api/plans/review      approve, send back or withdraw many plans at once
GET  /api/reviews           just the decisions for a date range (cheap: the calendar colours its days with it)
GET  /api/forecast/days     one meal slot over several days, dish by dish
GET  /api/activity          what happened lately; /api/activity/version changes whenever something is saved
"""

from datetime import date as Date
from datetime import timedelta
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api import services
from api.deps import get_service
from api.schemas import Scope, Slot, check_date
from feedforward import config as C
from feedforward.admin import activity, automation
from feedforward.admin.review_log import append_review, review_index
from feedforward.admin.store import AUTO_SOURCE, get_store
from feedforward.models.forecast_service import ForecastService
from feedforward.models.week_view import _calendar_flags

router = APIRouter()
MAX_DAYS = 14


def _window(start: Date | None, days: int) -> list[Date]:
    first = start or services.today()
    check_date(first)
    last = min(first + timedelta(days=days - 1), Date.fromisoformat(C.FORECAST_LAST_DAY))
    return [first + timedelta(days=i) for i in range((last - first).days + 1)]


def _light(review: dict | None) -> dict | None:
    """A decision without the per dish quantities (enough for lists)."""
    return None if review is None else {k: v for k, v in review.items() if k != "approved"}


def _logged() -> dict[tuple[str, str], dict]:
    """(date, slot) -> rows logged and whether the automation filled them."""
    kit = get_store().read("kitchen_log")
    out: dict[tuple[str, str], dict] = {}
    for (d, s), g in kit.groupby(["date", "meal_slot"]):
        out[(str(d), s)] = {"rows": len(g), "auto": bool((g["data_source"] == AUTO_SOURCE).all())}
    return out


@router.get("/plans")
def plans(start: Date | None = Query(None, description="default: today"), days: int = Query(7, ge=1, le=MAX_DAYS),
          svc: ForecastService = Depends(get_service)) -> dict:
    """Every meal from `start` for `days` days: main dish totals, risk, the standing decision and the log status."""
    index, logged, flags = review_index(), _logged(), _calendar_flags()
    out, counts = [], {"approve": 0, "send_back": 0, "pending": 0, "automatic": 0, "logged": 0}
    for day in _window(start, days):
        iso, slots, facts = str(day), [], {}
        for slot in C.MEAL_SLOTS:
            plan = services.scoped(svc.forecast(day, slot), "core")
            facts = facts or plan.get("day_facts", {})
            review = index.get((iso, slot))
            has_menu = bool(plan["dishes"])
            if has_menu:
                counts[review["decision"] if review else "pending"] += 1
                counts["automatic"] += bool(review and review["automatic"])
                counts["logged"] += (iso, slot) in logged
            slots.append({"meal_slot": slot, "has_menu": has_menu, "expected_attendance": plan["expected_attendance"],
                          "totals": plan["totals"], "dishes": len(plan["dishes"]), "dishes_hidden": plan["dishes_hidden"],
                          "risk_counts": {lvl: sum(d["surplus_risk"] == lvl for d in plan["dishes"]) for lvl in ("high", "medium", "low")},
                          "review": _light(review), "logged": logged.get((iso, slot))})
        f = flags.loc[pd.Timestamp(day)] if pd.Timestamp(day) in flags.index else None
        out.append({"date": iso, "weekday": day.strftime("%A"), "is_today": day == services.today(), "slots": slots,
                    "facts": {"exam_week": bool(facts.get("exam_week")), "holiday": bool(facts.get("holiday")),
                              "festival": bool(facts.get("festival")), "rain_level": facts.get("rain_level", 0),
                              "students_mostly_away": bool(facts.get("students_mostly_away")),
                              "formative_test": bool(f is not None and f["formative_test_any"])}})
    total = counts["approve"] + counts["send_back"] + counts["pending"]
    return {"start": out[0]["date"] if out else None, "today": str(services.today()), "days": out,
            "summary": {"plans": total, "approved": counts["approve"], "sent_back": counts["send_back"],
                        "pending": counts["pending"], "approved_automatically": counts["automatic"], "logged": counts["logged"]},
            "automation": automation.status()}


class PlanRef(BaseModel):
    date: Date
    meal_slot: Slot


class ManyReviewIn(BaseModel):
    """POST /api/plans/review. Approve keeps a plan that is already approved as it is (its quantities may have been
    changed by hand); use withdraw first to start that plan again."""

    items: list[PlanRef] = Field(min_length=1, max_length=60)
    decision: Literal["approve", "send_back", "withdraw"]
    reviewer: str | None = Field(None, max_length=80)
    note: str | None = Field(None, max_length=500)


@router.post("/plans/review")
def review_many(body: ManyReviewIn, svc: ForecastService = Depends(get_service)) -> dict:
    """The same decision for many plans. Plans with no dishes, and approvals of plans already approved, are skipped."""
    index, done, skipped = review_index(), [], []
    for it in body.items:
        check_date(it.date)
        ref = {"date": str(it.date), "meal_slot": it.meal_slot}
        standing = index.get((ref["date"], it.meal_slot))
        if (body.decision == "approve" and standing and standing["decision"] == "approve") or (
                body.decision == "withdraw" and standing is None):
            skipped.append(ref)
            continue
        plan = svc.forecast(it.date, it.meal_slot)
        if not plan["dishes"] or not append_review(plan, body.decision, body.reviewer, body.note, svc.bundle.info):
            skipped.append(ref)
            continue
        done.append(ref)
    verb = {"approve": "Approved", "send_back": "Sent back", "withdraw": "Withdrew the decision on"}[body.decision]
    message = f"{verb} {len(done)} plan{'' if len(done) == 1 else 's'}." if done else "Nothing needed changing."
    if done and skipped:
        message += f" {len(skipped)} left as they were."
    return {"done": done, "skipped": skipped, "message": message}


@router.get("/reviews")
def reviews(start: Date, end: Date) -> dict:
    """{date: {meal slot: decision summary}} for every reviewed plan from start to end (at most 62 days)."""
    if end < start or (end - start).days > 62:
        raise ValueError("Choose an end date on or after the start date, at most 62 days later.")
    out: dict[str, dict] = {}
    for (d, slot), r in review_index().items():
        if str(start) <= d <= str(end):
            out.setdefault(d, {})[slot] = _light(r)
    return {"start": str(start), "end": str(end), "reviews": out}


@router.get("/forecast/days")
def forecast_days(slot: Slot = "lunch", start: Date | None = Query(None, description="default: tomorrow"),
                  days: int = Query(7, ge=1, le=MAX_DAYS), scope: Scope = "core",
                  svc: ForecastService = Depends(get_service)) -> dict:
    """One meal slot over several days: the day totals and, for every dish, its numbers on each day it is served."""
    index = review_index()
    out_days, dishes = [], {}
    for day in _window(start or services.today() + timedelta(days=1), days):
        plan = services.plan_response(svc, day, slot, None, scope)
        out_days.append({"date": plan["date"], "weekday": plan["weekday"], "expected_attendance": plan["expected_attendance"],
                         "totals": plan["totals"], "risk_counts": plan["risk_counts"], "facts": plan["day_facts"],
                         "headline": plan["headline"] if plan["dishes"] else "", "review": _light(index.get((plan["date"], slot)))})
        for d in plan["dishes"]:
            row = dishes.setdefault(d["dish_id"], {"dish_id": d["dish_id"], "dish_name": d["dish_name"], "days": {}})
            row["days"][plan["date"]] = {k: d[k] for k in ("p10", "p50", "p90", "recommended", "usual_plan", "surplus_risk")}
    rows = sorted(dishes.values(), key=lambda r: (-len(r["days"]), -sum(c["recommended"] for c in r["days"].values())))
    return {"meal_slot": slot, "scope": scope, "days": out_days, "dishes": rows}


@router.get("/activity")
def recent_activity(limit: int = Query(20, ge=1, le=100)) -> dict:
    """Decisions, Daily log saves and automatic runs, newest first."""
    return activity.recent(limit)


@router.get("/activity/version")
def activity_version() -> dict:
    """Changes whenever a decision, a log entry or an automatic run is saved."""
    return {"version": activity.version()}
