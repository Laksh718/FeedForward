"""Feature registry: every model input with its definition and whether it is leakage safe.

Leakage rule: a forecast for day D may only use what is known before D is decided. Same day
prepared, topup, consumed, unmet, leftover, attendance and students_present are NEVER inputs.
Past values (lags of at least 7 days) are allowed.
"""

from dataclasses import dataclass

LAGS = (7, 14, 21)
MEAL_SLOTS = ("breakfast", "lunch", "snacks", "dinner")
PHASE_GROUPS = ("classes", "formative", "practical", "theory", "study_gap", "away", "enrolment")
TEXT_DIM = 8

# Columns that exist only after the day has happened. Never allowed as inputs.
BANNED_INPUTS = frozenset({
    "prepared_qty", "topup_qty", "consumed_qty", "unmet_qty", "leftover_qty", "leftover_kg",
    "attendance", "students_present", "demand_qty",
})


@dataclass(frozen=True)
class Feature:
    """One registry row."""

    name: str
    group: str
    definition: str
    leakage_safe: bool = True


def _build() -> list[Feature]:
    """List every model input feature."""
    f: list[Feature] = []

    def add(group: str, names: list[str] | str, definition: str) -> None:
        for n in [names] if isinstance(names, str) else names:
            f.append(Feature(n, group, definition))

    add("calendar", ["dow_sin", "dow_cos"], "Weekday as a point on a circle, so Sunday sits next to Monday")
    add("calendar", ["month_sin", "month_cos"], "Month as a point on a circle")
    add("calendar", ["is_weekend", "tn_public_holiday", "major_festival", "special_declared_holiday",
                     "compensatory_working_day", "rain_holiday_colleges"], "Calendar flag (0 or 1)")
    add("calendar", "days_to_next_holiday", "Days until the next public or declared holiday (cap 60)")
    add("calendar", "days_since_last_holiday", "Days since the last public or declared holiday (cap 60)")
    for cohort in ("senior", "first"):
        add("calendar", [f"{cohort}_{g}" for g in PHASE_GROUPS],
            f"One hot academic phase of the {cohort} cohort (second to fourth years or first years)")
    add("calendar", ["university_exam_any", "formative_test_any", "students_mostly_away"], "Exam or away flag")
    add("calendar", "phase_confidence_rank", "0 official, 1 probable, 2 estimated (exam end dates are estimates)")
    add("weather", ["temp_max_c", "temp_min_c", "temp_mean_c"], "Temperature in C (forecast noise added in training)")
    add("weather", "rain_level", "0 none, 1 light, 2 moderate or thunder, 3 heavy (mm is unusable)")
    add("weather", "hot_day", "1 when max temperature is at least 36 C")
    add("weather", "weather_reliable", "0 for the unverified February rows (copies of March)")
    add("weather", "weather_assumed", "1 when weather is last year's monthly average, not a forecast")
    add("menu", [f"slot_{s}" for s in MEAL_SLOTS], "One hot meal slot")
    add("menu", ["category_code", "diet_code"], "Integer code of dish category or diet")
    add("menu", ["popularity_score", "portion_g"], "Dish catalogue value (estimated)")
    add("menu", ["is_choice", "n_options"], "Dish is one of several alternatives, and how many")
    add("menu", ["special_limited", "is_core", "is_briyani_special"],
        "Limited stock dish; core forecast dish; served only on the 2nd and 4th Wednesday")
    add("menu", [f"text_emb_{i}" for i in range(TEXT_DIM)], "TF-IDF then SVD embedding of the dish name")
    add("history", [f"demand_lag_{n}" for n in LAGS], "Demand of the same dish and slot n days earlier")
    add("history", ["demand_mean3", "demand_std3", "demand_trend"],
        "Mean and spread of the last 3 same weekdays; lag 7 minus lag 14")
    add("history", [f"rate_lag_{n}" for n in LAGS], "Demand per attendee n days earlier")
    add("history", "rate_mean3", "Mean demand per attendee over the lags")
    add("history", ["leftover_rate_mean3", "unmet_rate_mean3"],
        "Past leftover share of cooked food; past share of demand not served")
    add("history", [f"has_lag_{n}" for n in LAGS], "1 when the lag exists (dish served that day)")
    add("history", "n_lags", "How many of the 3 lags exist (0 means no past for this dish yet)")
    add("history", [f"slot_att_lag_{n}" for n in LAGS], "Slot attendance n days earlier")
    add("history", "slot_att_mean3", "Mean slot attendance over the lags")
    return f


REGISTRY = _build()
FEATURE_COLUMNS = [x.name for x in REGISTRY]
BANNED_REGISTRY = [Feature(n, "banned", "Known only after the day happens", False) for n in sorted(BANNED_INPUTS)]
