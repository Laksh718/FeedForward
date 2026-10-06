"""GET /api/health"""

from datetime import timedelta

from fastapi import APIRouter, Depends

from api import services
from api.deps import get_service
from feedforward import config as C
from feedforward.models.forecast_service import ForecastService

router = APIRouter()


@router.get("/health")
def health(svc: ForecastService = Depends(get_service)) -> dict:
    """Service status, the project's today, the default plan date and the data source chip text."""
    today = services.today()
    return {"status": "ok", "today": str(today), "default_plan_date": str(today + timedelta(days=1)),
            "history_last_day": str(svc.history["date"].max().date()), "meal_slots": list(C.MEAL_SLOTS),
            "model": svc.bundle.info, "data_source_chip": services.DATA_SOURCE_CHIP, "data_source_short": "Simulated history",
            "data_note": "Kitchen history is simulated. Menu, calendar and weather are real; recipes and popularity are estimated."}
