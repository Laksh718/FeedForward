"""GET /api/plan and GET /api/week"""

from datetime import date as Date
from datetime import timedelta

from fastapi import APIRouter, Depends, Query

from api import services
from api.deps import get_service
from api.schemas import Scope, Slot, check_date
from feedforward.models.forecast_service import ForecastService

router = APIRouter()


@router.get("/plan")
def plan(date: Date = Query(None, description="default: tomorrow"), slot: Slot = "lunch", scope: Scope = "core",
         svc: ForecastService = Depends(get_service)) -> dict:
    """Per dish range, recommended quantity, usual plan and surplus risk, plus the headline sentences."""
    day = date or services.today() + timedelta(days=1)
    check_date(day)
    return services.plan_response(svc, day, slot, None, scope)


@router.get("/week")
def week(slot: Slot = "lunch", start: Date = Query(None, description="default: tomorrow"), scope: Scope = "core",
         dish_id: str | None = None, svc: ForecastService = Depends(get_service)) -> dict:
    """Seven day totals (or one dish) with the likely range, plus the actuals of the 7 days before."""
    first = start or services.today() + timedelta(days=1)
    check_date(first)
    check_date(first + timedelta(days=6))
    return services.week_response(svc, first, slot, scope, dish_id)
