"""Context builder: admin entered day information flows into the feature row exactly like the calendar and
weather columns of the dataset. Used for today, past dates entered later and future dates (expected weather,
special days). Reads the stored day context; it does not need the forecast code."""

import pandas as pd

from feedforward.admin.store import get_store
from feedforward.data.weather_types import WEATHER_TYPE_RAIN_LEVEL

CLASSES = "classes"


def _flag(v) -> bool:
    return str(v) in ("1", "True", "true")


def day_context_rows() -> pd.DataFrame:
    """Stored (not deleted) day context rows with a real date column."""
    df = get_store().read("day_context")
    if df.empty:
        return df
    return df.assign(date=pd.to_datetime(df["date"])).set_index("date", drop=False)


def overlay_calendar(cal: pd.DataFrame) -> pd.DataFrame:
    """Apply admin special day, exam week and festival entries to calendar rows (same columns as the dataset)."""
    ctx = day_context_rows()
    if ctx.empty:
        return cal
    cal = cal.copy()
    for d, r in ctx.iterrows():
        i = cal.index[cal["date"] == d]
        if not len(i):
            continue
        set_ = {}
        if _flag(r["special_day"]):
            set_["special_declared_holiday"] = 1
            if r["special_day_type"] == "rain_holiday":
                set_["rain_holiday_colleges"] = 1
        if _flag(r["festival"]):
            set_["tn_public_holiday"] = 1
            set_["major_festival"] = int(r["festival_scale"] == "major")
        if _flag(r["exam_week"]):
            if r["exam_type"] == "university_exam":
                set_.update(university_exam_any=1, senior_phase="theory_exam_period", first_year_phase="theory_exam_period")
            else:
                set_.update(formative_test_any=1, senior_phase="formative_test_III", first_year_phase="formative_test_I")
        if set_:
            set_["phase_confidence"] = "official"   # entered by the admin, so not an estimate
            for col, value in set_.items():
                cal.loc[i, col] = value
    return cal


def overlay_weather(weather: pd.DataFrame) -> pd.DataFrame:
    """Apply admin entered temperatures and weather type to weather rows; they are then no longer assumed."""
    ctx = day_context_rows()
    if ctx.empty:
        return weather
    w = weather.copy()
    for d, r in ctx.iterrows():
        i = w.index[w["date"] == d]
        if not len(i):
            continue
        hi = pd.to_numeric(r["temp_max_c"], errors="coerce")
        lo = pd.to_numeric(r["temp_min_c"], errors="coerce")
        changed = False
        if pd.notna(hi):
            w.loc[i, "temp_max_c"], changed = hi, True
        if pd.notna(lo):
            w.loc[i, "temp_min_c"], changed = lo, True
        if changed:
            w.loc[i, "temp_mean_c"] = (w.loc[i, "temp_max_c"] + w.loc[i, "temp_min_c"]) / 2
        if r["condition"] in WEATHER_TYPE_RAIN_LEVEL:
            w.loc[i, "rain_level"], changed = WEATHER_TYPE_RAIN_LEVEL[r["condition"]], True
        if changed:
            w.loc[i, ["weather_assumed", "weather_reliable"]] = [0, 1]
    return w
