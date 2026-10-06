"""Calendar and weather for dates after 2026-10-05 (the dataset ends there).

The calendar is seeded with what is known from the SRM schedules and the Tamil Nadu holiday list.
Every phase has a confidence (probable or estimated). Future weather is last year's monthly
average, always flagged as assumed, unless the admin enters a real forecast.
"""

import pandas as pd

from feedforward import config as C

FUTURE_END = "2027-01-31"
CONFIDENCE_RANK = {"official": 0, "probable": 1, "estimated": 2}

# (start, end, phase, confidence)
SENIOR_PHASES = [
    ("2026-10-06", "2026-10-13", "formative_test_III", "probable"),
    ("2026-10-14", "2026-10-28", "classes", "probable"),
    ("2026-10-29", "2026-11-06", "formative_test_IV", "probable"),
    ("2026-11-07", "2026-11-20", "classes", "probable"),
    ("2026-11-21", "2026-11-24", "study_gap", "estimated"),
    ("2026-11-25", "2026-12-23", "theory_exam_period", "estimated"),
    ("2026-12-24", "2027-01-05", "semester_break", "estimated"),
    ("2027-01-06", "2027-01-10", "enrolment", "probable"),
    ("2027-01-11", FUTURE_END, "classes", "estimated"),
]
FIRST_YEAR_PHASES = [
    ("2026-10-06", "2026-10-13", "formative_test_I", "probable"),
    ("2026-10-14", "2026-12-07", "classes", "probable"),
    ("2026-12-08", "2026-12-13", "study_gap", "estimated"),
    ("2026-12-14", "2026-12-31", "theory_exam_period", "estimated"),
    ("2027-01-01", "2027-01-05", "semester_break", "estimated"),
    ("2027-01-06", "2027-01-10", "enrolment", "probable"),
    ("2027-01-11", FUTURE_END, "classes", "estimated"),
]
# date, name, major festival, confidence
HOLIDAYS = [
    ("2026-10-19", "Ayudha Puja", 0, "probable"),
    ("2026-10-20", "Vijayadashami", 0, "probable"),
    ("2026-11-08", "Deepavali", 1, "probable"),
    ("2026-12-25", "Christmas", 0, "probable"),
]
EXAM_PHASES = {"practical_exam", "arrear_practical", "theory_exam_period"}
AWAY_PHASES = {"semester_break", "summer_semester"}


def _phase_series(spec: list[tuple], dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Expand (start, end, phase, confidence) ranges to one row per date."""
    out = pd.DataFrame({"date": dates, "phase": "classes", "conf": "estimated"})
    for start, end, phase, conf in spec:
        mask = (out["date"] >= start) & (out["date"] <= end)
        out.loc[mask, ["phase", "conf"]] = [phase, conf]
    return out


def build_future_calendar() -> pd.DataFrame:
    """Build the calendar table (same columns as calendar_real.csv) for the future period."""
    dates = pd.date_range(pd.Timestamp(C.HISTORY_END) + pd.Timedelta(days=1), FUTURE_END)
    senior, first = _phase_series(SENIOR_PHASES, dates), _phase_series(FIRST_YEAR_PHASES, dates)
    cal = pd.DataFrame({"date": dates})
    cal["day_of_week"] = dates.day_name()
    cal["is_weekend"] = (dates.dayofweek >= 5).astype(int)
    cal["week_of_year"] = dates.isocalendar().week.to_numpy()
    cal["month"] = dates.month
    hol = pd.DataFrame(HOLIDAYS, columns=["date", "holiday_name", "major_festival", "hconf"])
    hol["date"] = pd.to_datetime(hol["date"])
    cal = cal.merge(hol, on="date", how="left")
    cal["tn_public_holiday"] = cal["holiday_name"].notna().astype(int)
    cal["holiday_name"] = cal["holiday_name"].fillna("")
    cal["major_festival"] = cal["major_festival"].fillna(0).astype(int)
    for col in ("special_declared_holiday", "compensatory_working_day", "rain_holiday_colleges",
                "rain_holiday_schools_only"):
        cal[col] = 0
    cal["senior_phase"], cal["first_year_phase"] = senior["phase"].to_numpy(), first["phase"].to_numpy()
    conf = pd.concat([senior["conf"], first["conf"], cal["hconf"].fillna("official")], axis=1)
    rank = conf.apply(lambda col: col.map(CONFIDENCE_RANK)).max(axis=1)
    cal["phase_confidence"] = rank.map({v: k for k, v in CONFIDENCE_RANK.items()}).to_numpy()
    both = pd.concat([cal["senior_phase"], cal["first_year_phase"]], axis=1)
    cal["university_exam_any"] = both.isin(EXAM_PHASES).any(axis=1).astype(int)
    cal["formative_test_any"] = both.apply(lambda c: c.str.startswith("formative")).any(axis=1).astype(int)
    cal["students_mostly_away"] = cal["senior_phase"].isin(AWAY_PHASES).astype(int)
    cal["event_note"] = "Future date, seeded from SRM schedules; confidence in phase_confidence"
    cal["source_codes"] = "S2"
    return cal.drop(columns="hconf")


def weather_climatology(weather: pd.DataFrame) -> pd.DataFrame:
    """Monthly average of last year's reliable weather, used when no forecast is available."""
    ok = weather[weather["weather_reliable"] == 1]
    return ok.groupby(ok["date"].dt.month)[["temp_max_c", "temp_min_c", "rain_level"]].mean()


def assumed_weather(dates: pd.DatetimeIndex, weather: pd.DataFrame) -> pd.DataFrame:
    """Weather rows for dates without data: monthly climatology, flagged as assumed."""
    clim = weather_climatology(weather)
    months = pd.Series(dates.month, index=range(len(dates)))
    out = pd.DataFrame({"date": dates})
    out["temp_max_c"] = months.map(clim["temp_max_c"]).to_numpy()
    out["temp_min_c"] = months.map(clim["temp_min_c"]).to_numpy()
    out["temp_mean_c"] = (out["temp_max_c"] + out["temp_min_c"]) / 2
    out["rain_level"] = months.map(clim["rain_level"]).round().to_numpy()
    out["weather_reliable"] = 1
    out["weather_assumed"] = 1
    return out


def main() -> None:
    """Write data_store/calendar_future.csv."""
    cal = build_future_calendar()
    C.DATA_STORE_DIR.mkdir(exist_ok=True)
    cal.to_csv(C.CALENDAR_FUTURE_CSV, index=False, encoding="utf-8")
    print(f"wrote {C.CALENDAR_FUTURE_CSV.name}: {len(cal)} rows, {cal.date.min().date()} to {cal.date.max().date()}")


if __name__ == "__main__":
    main()
