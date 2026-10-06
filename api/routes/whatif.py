"""POST /api/whatif"""

from fastapi import APIRouter, Depends

from api import services
from api.deps import get_service
from api.schemas import WhatIfIn, check_date
from feedforward.models.forecast_service import ForecastService

router = APIRouter()


@router.post("/whatif")
def whatif(body: WhatIfIn, svc: ForecastService = Depends(get_service)) -> dict:
    """Plan with the given changes, next to the unchanged plan, so the difference is visible."""
    check_date(body.date)
    changed = services.plan_response(svc, body.date, body.meal_slot, body.overrides.to_domain(), body.scope)
    base = services.plan_response(svc, body.date, body.meal_slot, None, body.scope)
    delta = {k: changed["totals"][k] - base["totals"][k] for k in services.TOTAL_KEYS}
    return {"changed": changed, "baseline_totals": base["totals"], "difference": delta,
            "baseline_expected_attendance": base["expected_attendance"]}
