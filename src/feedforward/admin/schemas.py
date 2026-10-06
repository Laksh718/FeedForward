"""Validated shapes of a day's log entry. Messages are written for the person filling the form."""

from datetime import date as Date
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from feedforward import config as C
from feedforward.data.weather_types import WEATHER_TYPE_RAIN_LEVEL

Slot = Literal["breakfast", "lunch", "snacks", "dinner"]
SPECIAL_TYPES = ("holiday", "rain_holiday", "campus_event", "other")
EXAM_TYPES = ("formative_test", "university_exam")


class DayContextIn(BaseModel):
    """Day context: temperatures, weather type, special day, exam week and festival."""

    date: Date
    temp_max_c: float | None = Field(None, ge=C.TEMP_MIN_C, le=C.TEMP_MAX_C, description="degrees C")
    temp_min_c: float | None = Field(None, ge=C.TEMP_MIN_C, le=C.TEMP_MAX_C)
    weather_type: str | None = None
    special_day: bool = False
    special_day_type: Literal["holiday", "rain_holiday", "campus_event", "other"] | None = None
    special_day_name: str | None = Field(None, max_length=80)
    exam_week: bool = False
    exam_type: Literal["formative_test", "university_exam"] | None = None
    festival: bool = False
    festival_name: str | None = Field(None, max_length=80)
    festival_scale: Literal["major", "minor"] | None = None

    @model_validator(mode="after")
    def _check(self) -> "DayContextIn":
        if self.temp_max_c is not None and self.temp_min_c is not None and self.temp_min_c > self.temp_max_c:
            raise ValueError("The minimum temperature cannot be above the maximum temperature.")
        if self.weather_type and self.weather_type not in WEATHER_TYPE_RAIN_LEVEL:
            raise ValueError(f"Weather type must be one of: {', '.join(sorted(WEATHER_TYPE_RAIN_LEVEL))}.")
        if self.special_day and not (self.special_day_type and self.special_day_name):
            raise ValueError("For a special day, choose its type and give it a name.")
        if self.exam_week and not self.exam_type:
            raise ValueError("For an exam week, choose formative test or university exam.")
        if self.festival and not (self.festival_name and self.festival_scale):
            raise ValueError("For a festival, give its name and say whether it is major or minor.")
        return self


class AttendanceIn(BaseModel):
    """People who ate in a meal slot, and optionally how many students were on campus."""

    meal_slot: Slot
    attendance: int = Field(ge=0, le=C.ENROLLED, description=f"people who ate (at most {C.ENROLLED} enrolled)")
    students_present: int | None = Field(None, ge=0, le=C.ENROLLED)


class KitchenRowIn(BaseModel):
    """One dish in one slot: what was prepared and what happened to it. Consumed or leftover is required."""

    meal_slot: Slot
    dish_id: str = Field(pattern=r"^D\d{3}$")
    prepared_qty: int = Field(ge=0, le=50000)
    topup_qty: int = Field(0, ge=0, le=50000)
    consumed_qty: int | None = Field(None, ge=0, le=50000)
    leftover_qty: int | None = Field(None, ge=0, le=50000)
    ran_out_early: bool = False
    unmet_qty: int | None = Field(None, ge=0, le=50000, description="estimated portions wanted but not served")

    @model_validator(mode="after")
    def _check(self) -> "KitchenRowIn":
        supply = self.prepared_qty + self.topup_qty
        if self.consumed_qty is None and self.leftover_qty is None:
            raise ValueError("Enter either the portions eaten or the portions left over. Without one of them this row cannot be used for learning.")
        if self.consumed_qty is not None and self.consumed_qty > supply:
            raise ValueError("Portions eaten cannot be more than prepared plus top up.")
        if self.leftover_qty is not None and self.leftover_qty > supply:
            raise ValueError("Portions left over cannot be more than prepared plus top up.")
        if None not in (self.consumed_qty, self.leftover_qty) and self.consumed_qty + self.leftover_qty != supply:
            raise ValueError("Eaten plus left over should equal prepared plus top up. Enter only one of them, or fix the numbers.")
        if self.unmet_qty and not self.ran_out_early:
            raise ValueError("Unmet portions only make sense when the dish ran out early. Switch on 'ran out early' or clear the number.")
        return self


class IngredientIn(BaseModel):
    """Kilograms of one ingredient used in the day."""

    ingredient: str = Field(min_length=2, max_length=60)
    used_kg: float = Field(ge=0, le=20000)

    @field_validator("ingredient")
    @classmethod
    def _lower(cls, v: str) -> str:
        return v.strip().lower()


class DaySaveIn(BaseModel):
    """Everything entered for one date. Saving again for the same date updates the earlier entry."""

    date: Date
    entered_by: str | None = Field(None, max_length=60)
    context: DayContextIn | None = None
    attendance: list[AttendanceIn] = []
    kitchen: list[KitchenRowIn] = []
    ingredients: list[IngredientIn] = []

    @model_validator(mode="after")
    def _check(self) -> "DaySaveIn":
        if self.context and self.context.date != self.date:
            raise ValueError("The day context date does not match the date of the entry.")
        slots = [a.meal_slot for a in self.attendance]
        if len(slots) != len(set(slots)):
            raise ValueError("Each meal slot can have only one attendance number.")
        keys = [(k.meal_slot, k.dish_id) for k in self.kitchen]
        if len(keys) != len(set(keys)):
            raise ValueError("A dish appears twice in the same meal slot. Keep one row per dish and slot.")
        names = [i.ingredient for i in self.ingredients]
        if len(names) != len(set(names)):
            raise ValueError("An ingredient appears twice. Keep one row per ingredient.")
        return self


class DeleteIn(BaseModel):
    """Soft delete: the row stays in the file, marked deleted, and is ignored everywhere."""

    table: Literal["day_context", "attendance", "kitchen_log", "ingredient_usage"]
    date: Date
    meal_slot: Slot | None = None
    dish_id: str | None = None
    ingredient: str | None = None


class RecipeFillIn(BaseModel):
    """Prepared portions per dish, used to pre fill ingredient quantities from the recipes."""

    rows: list[dict] = Field(max_length=200)
