"""POST /api/review (the human decision) and GET /api/review (its status)."""

from datetime import date as Date

from fastapi import APIRouter, Depends

from api import services
from api.deps import get_service
from api.schemas import ReviewIn, Slot, check_date
from feedforward.admin.review_log import append_review, latest_review
from feedforward.models.forecast_service import ForecastService

router = APIRouter()


@router.post("/review")
def review(body: ReviewIn, svc: ForecastService = Depends(get_service)) -> dict:
    """Approve or send back a plan. The forecast is recomputed here and stored as a snapshot with the decision."""
    check_date(body.date)
    plan = services.plan_response(svc, body.date, body.meal_slot, body.overrides.to_domain(), "all")
    rows = append_review(plan, body.decision, body.reviewer, body.note, svc.bundle.info)
    return {"stored_rows": rows, "review": latest_review(plan["date"], body.meal_slot),
            "message": "Plan approved and saved." if body.decision == "approve" else "Plan sent back and saved."}


@router.get("/review")
def review_status(date: Date, slot: Slot) -> dict:
    """Latest decision for a date and slot, or null when nobody has reviewed it yet."""
    return {"review": latest_review(str(date), slot)}
