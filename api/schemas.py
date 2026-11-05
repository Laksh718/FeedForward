"""Request models (validated by Pydantic). Responses are plain dictionaries built in api/services.py."""

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from feedforward import config as C
from feedforward.data.features import WEATHER_TYPE_RAIN_LEVEL
from feedforward.models.forecast_service import Overrides

Slot = Literal["breakfast", "lunch", "snacks", "dinner"]
Scope = Literal["core", "all"]
MAX_ATTENDANCE = 4000  # enrolled students


class OverridesIn(BaseModel):
    """What if settings sent by the dashboard. Missing means unchanged."""

    attendance_change_pct: float | None = Field(None, ge=-90, le=100, description="percent change in attendance")
    expected_attendance: float | None = Field(None, gt=0, le=MAX_ATTENDANCE)
    special_day: bool | None = None
    exam_week: bool | None = None
    festival: bool | None = None
    temp_max_c: float | None = Field(None, ge=10, le=50)
    temp_min_c: float | None = Field(None, ge=10, le=50)
    weather_type: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "OverridesIn":
        if self.weather_type is not None and self.weather_type not in WEATHER_TYPE_RAIN_LEVEL:
            raise ValueError(f"weather_type must be one of {sorted(WEATHER_TYPE_RAIN_LEVEL)}")
        if self.temp_max_c is not None and self.temp_min_c is not None and self.temp_min_c > self.temp_max_c:
            raise ValueError("The minimum temperature cannot be above the maximum temperature.")
        return self

    def to_domain(self) -> Overrides:
        """Convert to the forecast service's own type."""
        return Overrides(**self.model_dump())


class WhatIfIn(BaseModel):
    """POST /api/whatif"""

    date: Date
    meal_slot: Slot
    scope: Scope = "core"
    overrides: OverridesIn = OverridesIn()


class ReviewIn(BaseModel):
    """POST /api/review: the human decision. The server recomputes the forecast, so numbers are never trusted from the client."""

    date: Date
    meal_slot: Slot
    decision: Literal["approve", "send_back", "withdraw"]
    scope: Scope = "core"
    reviewer: str | None = Field(None, max_length=80)
    note: str | None = Field(None, max_length=500)
    overrides: OverridesIn = OverridesIn()
    adjusted_quantities: dict[str, int] = Field(default_factory=dict, description="dish_id to portions the reviewer changed")

    @model_validator(mode="after")
    def _check_quantities(self) -> "ReviewIn":
        if any(q < 0 or q > 20000 for q in self.adjusted_quantities.values()):
            raise ValueError("Quantities must be between 0 and 20,000 portions.")
        return self


def check_date(day: Date) -> None:
    """Reject dates the calendar does not cover, with a message that says how to fix it."""
    if day < Date.fromisoformat(C.HISTORY_START) or day > Date.fromisoformat(C.FORECAST_LAST_DAY):
        raise ValueError(f"No calendar for {day}. Choose a date from {C.HISTORY_START} to {C.FORECAST_LAST_DAY}.")
