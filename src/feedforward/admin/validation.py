"""Sanity warnings for an entry (not blockers): is each value unusual compared with what the model expected?

This is the same idea as autoencoder anomaly detection through reconstruction error: a value far from what the
model expects for that date is probably a typo (an extra digit, a wrong slot). Here "expected" is the widened
forecast range for that date, slot and dish; there is no separate network to train.
"""

from datetime import date as Date

import pandas as pd

from feedforward import config as C
from feedforward.admin.schemas import DayContextIn, DaySaveIn
from feedforward.models.forecast_service import ForecastService, Overrides

SPREAD_FACTOR = 3.0          # how many times wider than the forecast range a value may be before we warn
ATTENDANCE_BAND = (0.6, 1.4)  # attendance outside 60 to 140 percent of the expected number is flagged
PREPARED_BAND = (0.4, 2.5)    # prepared quantity outside 0.4 to 2.5 times the most likely demand is flagged
INGREDIENT_BAND = (0.2, 3.0)  # ingredient use outside 0.2 to 3 times the usual daily use is flagged


def overrides_from_context(ctx: DayContextIn | None) -> Overrides:
    """The entered day information as forecast settings (what the model should assume for that date)."""
    if ctx is None:
        return Overrides()
    return Overrides(special_day=True if ctx.special_day else None, exam_week=True if ctx.exam_week else None,
                     festival=True if ctx.festival else None, temp_max_c=ctx.temp_max_c, temp_min_c=ctx.temp_min_c,
                     weather_type=ctx.weather_type)


def _warn(field: str, message: str, severity: str = "warning") -> dict:
    return {"field": field, "severity": severity, "message": message}


def widened(p10: int, p50: int, p90: int) -> tuple[float, float]:
    """The forecast range stretched on both sides, the limits beyond which a value looks like a typo."""
    return max(0.0, p50 - SPREAD_FACTOR * (p50 - p10)), p50 + SPREAD_FACTOR * (p90 - p50)


def check_future(entry: DaySaveIn, today: Date) -> None:
    """Future dates may only hold expected weather and special day information."""
    if entry.date > today and (entry.attendance or entry.kitchen or entry.ingredients):
        raise ValueError(f"{entry.date} is in the future. For future dates you can only enter expected weather and special day "
                         "information. Attendance, dishes and ingredients can be entered once the day has happened.")


def sanity_warnings(entry: DaySaveIn, svc: ForecastService, ingredient_master: pd.DataFrame) -> list[dict]:
    """Warnings for values that are far from what was expected. They never stop a save."""
    out: list[dict] = []
    ov = overrides_from_context(entry.context)
    plans = {}

    def plan(slot: str) -> dict:
        if slot not in plans:
            plans[slot] = svc.forecast(entry.date, slot, overrides=ov, n_samples=200)
        return plans[slot]

    if str(entry.date) <= C.HISTORY_END and (entry.kitchen or entry.attendance):
        out.append(_warn("date", f"{entry.date} already has simulated history. Your real entry will replace it for learning.", "info"))
    entered_att = {a.meal_slot for a in entry.attendance}
    for a in entry.attendance:
        exp = plan(a.meal_slot)["expected_attendance"]
        lo, hi = exp * ATTENDANCE_BAND[0], exp * ATTENDANCE_BAND[1]
        if exp and not lo <= a.attendance <= hi:
            out.append(_warn(f"attendance.{a.meal_slot}", f"{a.attendance:,} people for {a.meal_slot} is far from the expected {exp:,}. "
                             "Check for a missing or extra digit."))
    for slot in sorted({k.meal_slot for k in entry.kitchen} - entered_att):
        out.append(_warn(f"attendance.{slot}", f"No attendance number for {slot}. The {slot} dish rows will be saved but cannot be used for learning."))
    for k in entry.kitchen:
        row = next((d for d in plan(k.meal_slot)["dishes"] if d["dish_id"] == k.dish_id), None)
        name = row["dish_name"] if row else k.dish_id
        if row is None:
            out.append(_warn(f"kitchen.{k.meal_slot}.{k.dish_id}", f"{name} is not on the {k.meal_slot} menu for this day. Saved as entered.", "info"))
            continue
        supply = k.prepared_qty + k.topup_qty
        eaten = k.consumed_qty if k.consumed_qty is not None else supply - (k.leftover_qty or 0)
        demand = eaten + (k.unmet_qty or 0)
        lo, hi = widened(row["p10"], row["p50"], row["p90"])
        where = f"kitchen.{k.meal_slot}.{k.dish_id}"
        if not lo <= demand <= hi:
            out.append(_warn(where, f"{name}: {demand:,} wanted is far outside the expected range of {row['p10']:,} to {row['p90']:,}. "
                             "Check for a typo, or ignore this if the day really was unusual."))
        if row["p50"] and not row["p50"] * PREPARED_BAND[0] <= k.prepared_qty <= row["p50"] * PREPARED_BAND[1]:
            out.append(_warn(where, f"{name}: {k.prepared_qty:,} prepared is far from the most likely demand of {row['p50']:,}."))
    use = ingredient_master.set_index("ingredient")["avg_daily_use_kg"]
    for i in entry.ingredients:
        if i.ingredient not in use.index:
            out.append(_warn(f"ingredient.{i.ingredient}", f"'{i.ingredient}' is not in the ingredient list. It will be saved as a new ingredient.", "info"))
        elif use[i.ingredient] and not use[i.ingredient] * INGREDIENT_BAND[0] <= i.used_kg <= use[i.ingredient] * INGREDIENT_BAND[1]:
            out.append(_warn(f"ingredient.{i.ingredient}", f"{i.used_kg:g} kg of {i.ingredient} is far from the usual {use[i.ingredient]:g} kg a day."))
    return out
