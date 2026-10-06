"""Feature engineering. All functions work for any date, so forecasting uses the same code.

Hand engineered here: calendar, weather, menu and lag features. The VAE later learns its own
dish embedding, which is the learned counterpart of the text embedding built here.
"""

import numpy as np
import pandas as pd

from feedforward import config as C
from feedforward.admin.context import overlay_calendar, overlay_weather
from feedforward.data.calendar_future import assumed_weather
from feedforward.data.feature_registry import LAGS, MEAL_SLOTS, PHASE_GROUPS
from feedforward.data.feature_registry import TEXT_DIM as _TEXT_DIM
from feedforward.data.weather_types import WEATHER_TYPE_RAIN_LEVEL  # noqa: F401  (also imported from here by other modules)

CAP_DAYS = 60
HOT_C = 36.0
WEATHER_NOISE_C = 1.5       # forecast error added to temperatures during training
RAIN_FLIP_PROB = 0.10       # chance that a forecast rain level is wrong by one step
PHASE_MAP = {
    "classes": "classes", "formative_test_I": "formative", "formative_test_II": "formative",
    "formative_test_III": "formative", "formative_test_IV": "formative",
    "practical_exam": "practical", "arrear_practical": "practical",
    "theory_exam_period": "theory", "study_gap": "study_gap", "semester_break": "away",
    "summer_semester": "away", "enrolment": "enrolment", "orientation": "enrolment",
}
CONFIDENCE_RANK = {"official": 0, "probable": 1, "estimated": 2}
CALENDAR_COLS = ["date", "tn_public_holiday", "major_festival", "special_declared_holiday",
                 "compensatory_working_day", "rain_holiday_colleges", "senior_phase", "first_year_phase",
                 "phase_confidence", "university_exam_any", "formative_test_any", "students_mostly_away"]


def full_calendar() -> pd.DataFrame:
    """Real calendar followed by the seeded future calendar."""
    real = pd.read_parquet(C.PROCESSED_DIR / "calendar.parquet")[CALENDAR_COLS]
    future = pd.read_csv(C.CALENDAR_FUTURE_CSV, parse_dates=["date"], encoding="utf-8")[CALENDAR_COLS]
    cal = pd.concat([real, future], ignore_index=True).sort_values("date").reset_index(drop=True)
    return overlay_calendar(cal)  # special days, exam weeks and festivals entered by the admin


def full_weather(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Weather for every requested date: real where known, last year's monthly average otherwise."""
    real = pd.read_parquet(C.PROCESSED_DIR / "weather.parquet")
    real = real.assign(weather_assumed=0)
    known = real[real["date"].isin(dates)]
    missing = dates.difference(pd.DatetimeIndex(known["date"]))
    parts = [known]
    if len(missing):
        parts.append(assumed_weather(pd.DatetimeIndex(missing), real))
    cols = ["date", "temp_max_c", "temp_min_c", "temp_mean_c", "rain_level", "weather_reliable", "weather_assumed"]
    out = pd.concat(parts)[cols].sort_values("date").reset_index(drop=True)
    return overlay_weather(out)  # temperatures and weather types entered by the admin


def _days_to_and_since(is_event: pd.Series, dates: pd.Series) -> tuple[np.ndarray, np.ndarray]:
    """Days until the next event day and since the last one (capped)."""
    event_days = dates[is_event.astype(bool)].to_numpy()
    nxt, since = np.full(len(dates), CAP_DAYS), np.full(len(dates), CAP_DAYS)
    for i, d in enumerate(dates.to_numpy()):
        after = event_days[event_days >= d]
        before = event_days[event_days <= d]
        if len(after):
            nxt[i] = min(CAP_DAYS, (after[0] - d) / np.timedelta64(1, "D"))
        if len(before):
            since[i] = min(CAP_DAYS, (d - before[-1]) / np.timedelta64(1, "D"))
    return nxt, since


def date_features(calendar: pd.DataFrame, weather: pd.DataFrame) -> pd.DataFrame:
    """One row per date with calendar and weather features (the same for any slot or dish)."""
    cal = calendar.copy()
    out = pd.DataFrame({"date": cal["date"]})
    dow, month = cal["date"].dt.dayofweek, cal["date"].dt.month
    out["dow_sin"], out["dow_cos"] = np.sin(2 * np.pi * dow / 7), np.cos(2 * np.pi * dow / 7)
    out["month_sin"], out["month_cos"] = np.sin(2 * np.pi * month / 12), np.cos(2 * np.pi * month / 12)
    out["is_weekend"] = (dow >= 5).astype(int)
    for col in ("tn_public_holiday", "major_festival", "special_declared_holiday",
                "compensatory_working_day", "rain_holiday_colleges", "university_exam_any",
                "formative_test_any", "students_mostly_away"):
        out[col] = cal[col].astype(int)
    holiday = (cal["tn_public_holiday"] | cal["special_declared_holiday"]).astype(int)
    out["days_to_next_holiday"], out["days_since_last_holiday"] = _days_to_and_since(holiday, cal["date"])
    for cohort, col in (("senior", "senior_phase"), ("first", "first_year_phase")):
        group = cal[col].map(PHASE_MAP)
        for g in PHASE_GROUPS:
            out[f"{cohort}_{g}"] = (group == g).astype(int)
    out["phase_confidence_rank"] = cal["phase_confidence"].map(CONFIDENCE_RANK).astype(int)
    out = out.merge(weather, on="date", how="left")
    out["hot_day"] = (out["temp_max_c"] >= HOT_C).astype(int)
    return out


def add_weather_noise(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Training only: perturb weather like a real forecast, so the model does not trust it fully."""
    df = df.copy()
    shift = rng.normal(0, WEATHER_NOISE_C, len(df))
    for col in ("temp_max_c", "temp_min_c", "temp_mean_c"):
        df[col] = df[col] + shift
    df["hot_day"] = (df["temp_max_c"] >= HOT_C).astype(int)
    flip = rng.random(len(df)) < RAIN_FLIP_PROB
    step = rng.choice([-1, 1], len(df))
    df["rain_level"] = np.where(flip, np.clip(df["rain_level"] + step, 0, 3), df["rain_level"])
    return df


def menu_rows_for(dates: pd.DatetimeIndex, weekly_menu: pd.DataFrame) -> pd.DataFrame:
    """Dishes served on each date, from the fixed weekly menu (briyani only on 2nd and 4th Wednesday)."""
    frames = []
    for d in dates:
        nth = (d.day - 1) // 7 + 1
        special_ok = d.dayofweek == 2 and nth in (2, 4)
        rows = weekly_menu[(weekly_menu["day_of_week"] == d.day_name())
                           & ((weekly_menu["condition"] == "always") | special_ok)]
        frames.append(rows.assign(date=d))
    out = pd.concat(frames, ignore_index=True)
    out["is_briyani_special"] = (out["condition"] != "always").astype(int)
    return out[["date", "meal_slot", "dish_id", "is_choice", "n_options", "is_briyani_special"]]


def dish_features(dishes: pd.DataFrame, history: pd.DataFrame) -> pd.DataFrame:
    """One row per dish: catalogue values, codes and the text embedding."""
    out = dishes[["dish_id", "popularity_score", "portion_g"]].copy()
    out["category_code"] = dishes["category"].astype("category").cat.codes
    out["diet_code"] = dishes["diet"].astype("category").cat.codes
    out["is_core"] = (dishes["forecast_priority"] == "core").astype(int)
    limited = history.groupby("dish_id")["special_limited"].max()
    out["special_limited"] = out["dish_id"].map(limited).fillna(0).astype(int)
    emb = [f"text_emb_{i}" for i in range(_TEXT_DIM)]
    out[emb] = dishes[emb].to_numpy()
    out["dish_idx"] = np.arange(len(dishes))
    return out


def _past_table(history: pd.DataFrame) -> pd.DataFrame:
    """Per row quantities that are only used with a lag of at least 7 days."""
    h = history.copy()
    h["demand"] = h["consumed_qty"] + h["unmet_qty"]
    h["rate"] = h["demand"] / h["attendance"]
    h["leftover_rate"] = h["leftover_qty"] / (h["prepared_qty"] + h["topup_qty"]).clip(lower=1)
    h["unmet_rate"] = h["unmet_qty"] / h["demand"].clip(lower=1)
    return h[["date", "meal_slot", "dish_id", "demand", "rate", "leftover_rate", "unmet_rate"]]


def lag_features(history: pd.DataFrame, targets: pd.DataFrame) -> pd.DataFrame:
    """History features for target rows (date, meal_slot, dish_id). Only lags of 7+ days are used."""
    past = _past_table(history)
    slot_att = history.groupby(["date", "meal_slot"], as_index=False)["attendance"].first()
    out = targets[["date", "meal_slot", "dish_id"]].copy()
    for lag in LAGS:
        shifted = past.assign(date=past["date"] + pd.Timedelta(days=lag))
        shifted.columns = ["date", "meal_slot", "dish_id"] + [f"{c}_lag_{lag}" for c in shifted.columns[3:]]
        out = out.merge(shifted, on=["date", "meal_slot", "dish_id"], how="left")
        att = slot_att.assign(date=slot_att["date"] + pd.Timedelta(days=lag)).rename(
            columns={"attendance": f"slot_att_lag_{lag}"})
        out = out.merge(att, on=["date", "meal_slot"], how="left")
        out[f"has_lag_{lag}"] = out[f"demand_lag_{lag}"].notna().astype(int)
    out["n_lags"] = out[[f"has_lag_{n}" for n in LAGS]].sum(axis=1)

    def mean_of(prefix: str) -> pd.Series:
        return out[[f"{prefix}_lag_{n}" for n in LAGS]].mean(axis=1)

    out["demand_mean3"], out["rate_mean3"] = mean_of("demand"), mean_of("rate")
    out["leftover_rate_mean3"], out["unmet_rate_mean3"] = mean_of("leftover_rate"), mean_of("unmet_rate")
    out["slot_att_mean3"] = mean_of("slot_att")
    out["demand_std3"] = out[[f"demand_lag_{n}" for n in LAGS]].std(axis=1)
    out["demand_trend"] = out["demand_lag_7"] - out["demand_lag_14"]
    for lag in LAGS:  # a missing lag is filled with the mean of the lags that exist (else 0)
        for prefix in ("demand", "rate", "slot_att"):
            col = f"{prefix}_lag_{lag}"
            out[col] = out[col].fillna(out[f"{prefix}_mean3"])
    keep = ["demand_std3", "demand_trend", "demand_mean3", "rate_mean3", "leftover_rate_mean3",
            "unmet_rate_mean3", "slot_att_mean3"]
    out[keep] = out[keep].fillna(0)
    lag_cols = [f"{p}_lag_{n}" for p in ("demand", "rate", "slot_att") for n in LAGS]
    out[lag_cols] = out[lag_cols].fillna(0)
    return out.drop(columns=[f"{p}_lag_{n}" for p in ("leftover_rate", "unmet_rate") for n in LAGS])


def build_features(targets: pd.DataFrame, history: pd.DataFrame, dishes: pd.DataFrame) -> pd.DataFrame:
    """All model inputs for target rows (date, meal_slot, dish_id, is_choice, n_options, is_briyani_special)."""
    cal = full_calendar()  # whole calendar, so "days to next holiday" can look past the target dates
    dfeat = date_features(cal, full_weather(pd.DatetimeIndex(cal["date"])))
    out = targets.merge(dfeat, on="date", how="left")
    out = out.merge(dish_features(dishes, history), on="dish_id", how="left")
    for s in MEAL_SLOTS:
        out[f"slot_{s}"] = (out["meal_slot"] == s).astype(int)
    out = out.merge(lag_features(history, targets), on=["date", "meal_slot", "dish_id"], how="left")
    return out
