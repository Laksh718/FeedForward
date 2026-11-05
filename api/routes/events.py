"""Rare event plans.

GET  /api/events        the event types, whether the GAN is trained, and the rare days coming up on the calendar
POST /api/events/plan   the plan for one meal under an event: the normal plan, the plan with the event, the demand
                        the GAN generates for it, the ingredients the change needs, and three quantities to choose from

Approving an event plan uses POST /api/review with the event's settings as `overrides` (see `approve_with`), so it is
saved, listed and compared like any other plan.
"""

from datetime import date as Date
from datetime import timedelta
from typing import Literal

import pandas as pd
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from api import services
from api.deps import get_service
from api.routes.calendar import _combined_calendar
from api.schemas import Slot, check_date
from feedforward import config as C
from feedforward.admin.review_log import append_review
from feedforward.models import rare_events
from feedforward.models.forecast_service import ForecastService
from feedforward.models.whatif_impact import impact

router = APIRouter()


def _upcoming(first: Date, days: int) -> list[dict]:
    """Festivals, holidays and the first day of each exam week from `first` on (the next `days` days)."""
    cal = _combined_calendar()
    cal = cal[(cal["date"] >= pd.Timestamp(first)) & (cal["date"] <= pd.Timestamp(first + timedelta(days=days)))].reset_index(drop=True)
    exam = cal["university_exam_any"].astype(bool)
    out = []
    for i, r in cal.iterrows():
        name = r["holiday_name"] if isinstance(r["holiday_name"], str) and r["holiday_name"] else None
        if r["major_festival"]:
            event, label = "festival", name or "Festival"
        elif r["tn_public_holiday"] or r["special_declared_holiday"]:
            event, label = "holiday", name or "Holiday"
        elif exam[i] and (i == 0 or not exam[i - 1]):
            event, label = "exam_week", "University exam week begins"
        else:
            continue
        out.append({"date": str(r["date"].date()), "weekday": r["date"].day_name(), "event": event, "name": label})
    return out


@router.get("/events")
def events(days: int = Query(120, ge=7, le=365)) -> dict:
    """What can be planned for, and the rare days on the calendar from today."""
    return {"types": [{"key": k, "label": v["label"], "about": v["about"]} for k, v in rare_events.EVENTS.items()],
            "gan_available": rare_events.gan_available(), "upcoming": _upcoming(services.today(), days),
            "today": str(services.today())}


class EventPlanIn(BaseModel):
    """POST /api/events/plan"""

    date: Date
    meal_slot: Slot
    event: str = Field(pattern="^(festival|holiday|exam_week|rain)$")
    attendance_change_pct: float | None = Field(None, ge=-60, le=60)


@router.post("/events/plan")
def event_plan(body: EventPlanIn, svc: ForecastService = Depends(get_service)) -> dict:
    """The event plan for one meal, its generated demand, and the quantities to choose from when approving."""
    check_date(body.date)
    return build_event_plan(svc, body.date, body.meal_slot, body.event, body.attendance_change_pct)


def build_event_plan(svc: ForecastService, day: Date, slot: str, event: str, attendance_change_pct: float | None) -> dict:
    """See event_plan."""
    ov = rare_events.event_overrides(event, attendance_change_pct)
    base = services.plan_response(svc, day, slot, None, "core")
    plan = services.plan_response(svc, day, slot, ov, "core")
    gen = rare_events.generate(svc, day, slot, event, attendance_change_pct)
    usual = {d["dish_id"]: d for d in base["dishes"]}
    rows, options = [], {"forecast": {}, "generated_typical": {}, "generated_high": {}}
    for d in plan["dishes"]:
        g = gen["dishes"].get(d["dish_id"])
        rows.append({**{k: d[k] for k in ("dish_id", "dish_name", "p10", "p50", "p90", "recommended", "usual_plan", "surplus_risk")},
                     "normal_recommended": usual.get(d["dish_id"], {}).get("recommended"), "generated": g,
                     "verdict": rare_events.verdict(d["recommended"], g)})
        options["forecast"][d["dish_id"]] = d["recommended"]
        options["generated_typical"][d["dish_id"]] = int(round(g["p50"] / 10) * 10) if g else d["recommended"]
        options["generated_high"][d["dish_id"]] = int(round(g["p90"] / 10) * 10) if g else d["recommended"]
    totals = {k: sum(v.values()) for k, v in options.items()}
    counts = {v: sum(r["verdict"] == v for r in rows) for v in ("covered", "may_run_short", "may_be_left_over")}
    info = rare_events.EVENTS[event]
    return {"date": plan["date"], "weekday": plan["weekday"], "meal_slot": slot, "event": event,
            "event_label": info["label"], "about": info["about"], "overrides": ov.applied(),
            "normal": {"totals": base["totals"], "expected_attendance": base["expected_attendance"]},
            "plan": {"totals": plan["totals"], "expected_attendance": plan["expected_attendance"], "headline": plan["headline"],
                     "supporting": plan["supporting"], "day_facts": plan["day_facts"], "notes": plan["notes"]},
            "dishes": rows, "generated": {k: gen[k] for k in ("available", "draws", "total", "note")},
            "verdicts": counts, "options": options, "option_totals": totals, "impact": impact(base, plan),
            "review": plan["review"],
            "approve_with": {"overrides": ov.applied(), "note": f"Rare event plan: {info['label']}."}}


class EventApproveIn(BaseModel):
    """POST /api/events/approve: approve the event plan of several days and meals at once (an exam week, say)."""

    start: Date
    days: int = Field(1, ge=1, le=14)
    meal_slots: list[Slot] = Field(min_length=1, max_length=4)
    event: str = Field(pattern="^(festival|holiday|exam_week|rain)$")
    option: Literal["forecast", "generated_typical", "generated_high"] = "forecast"
    attendance_change_pct: float | None = Field(None, ge=-60, le=60)
    reviewer: str | None = Field(None, max_length=80)


@router.post("/events/approve")
def event_approve(body: EventApproveIn, svc: ForecastService = Depends(get_service)) -> dict:
    """Approve the event plan of every chosen meal on every day of the range, with the chosen quantities. Each plan is
    saved like an approval on the Service board: the event settings as the what if and the quantities as changes."""
    last = min(body.start + timedelta(days=body.days - 1), Date.fromisoformat(C.FORECAST_LAST_DAY))
    check_date(body.start)
    ov = rare_events.event_overrides(body.event, body.attendance_change_pct)
    label = rare_events.EVENTS[body.event]["label"]
    done, total = [], 0
    day = body.start
    while day <= last:
        for slot in body.meal_slots:
            ep = build_event_plan(svc, day, slot, body.event, body.attendance_change_pct)
            if not ep["dishes"]:
                continue
            plan = services.plan_response(svc, day, slot, ov, "all")
            chosen = {k: v for k, v in ep["options"][body.option].items() if v != ep["options"]["forecast"][k]}
            append_review(plan, "approve", body.reviewer, f"Rare event plan: {label}.", svc.bundle.info, chosen)
            done.append({"date": str(day), "meal_slot": slot, "total": ep["option_totals"][body.option]})
            total += ep["option_totals"][body.option]
        day += timedelta(days=1)
    n = len(done)
    return {"done": done, "message": f"Approved {n} {label.lower()} plan{'' if n == 1 else 's'} ({total:,} portions of the main dishes)."
            if n else "No meals with dishes in that range, so nothing was approved."}
