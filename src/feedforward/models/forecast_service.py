"""One clean entry point for forecasts: forecast(date, meal_slot, dish_ids, overrides, n_samples).

Plain Python does all the work: build features, run the CVAE, compute the usual plan and the recommendation.
No language model is involved here; the copilot only explains the numbers this module returns.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd

from feedforward import config as C
from feedforward.data.feature_registry import PHASE_GROUPS
from feedforward.data.features import WEATHER_TYPE_RAIN_LEVEL, build_features, menu_rows_for
from feedforward.models.baselines import usual_plan
from feedforward.models.bundle import ModelBundle
from feedforward.models.metrics import round_portions
from feedforward.models.train import FINAL_DIR
from feedforward.plugins.surplus_detector_stub import StubSurplusDetector, SurplusDetector

TOTALS_NOTE = "P10 and P90 totals add dish ranges, so they form a wider band than the true range of the total."


@dataclass
class Overrides:
    """What if settings. Anything left as None is not changed."""

    attendance_change_pct: float | None = None   # +15 means 15 percent more people than expected
    expected_attendance: float | None = None     # replaces the attendance forecast for the slot
    special_day: bool | None = None              # declared holiday or campus event
    exam_week: bool | None = None
    festival: bool | None = None
    temp_max_c: float | None = None
    temp_min_c: float | None = None
    weather_type: str | None = None              # one of WEATHER_TYPE_RAIN_LEVEL

    def applied(self) -> dict:
        """Only the settings that were actually given."""
        return {k: v for k, v in self.__dict__.items() if v is not None}


def apply_date_overrides(feats: pd.DataFrame, ov: Overrides) -> pd.DataFrame:
    """Change calendar and weather columns the same way real calendar entries would."""
    f = feats.copy()
    if ov.exam_week is not None:
        f["university_exam_any"], f["formative_test_any"] = int(ov.exam_week), 0
        f["students_mostly_away"] = 0
        for cohort in ("senior", "first"):
            for g in PHASE_GROUPS:
                f[f"{cohort}_{g}"] = int((g == "theory") if ov.exam_week else (g == "classes"))
    if ov.special_day is not None:
        f["special_declared_holiday"] = int(ov.special_day)
    if ov.festival is not None:
        f["major_festival"], f["tn_public_holiday"] = int(ov.festival), int(ov.festival)
    if ov.special_day or ov.festival:
        f["days_to_next_holiday"], f["days_since_last_holiday"] = 0, 0
    if ov.temp_max_c is not None:
        f["temp_max_c"] = ov.temp_max_c
    if ov.temp_min_c is not None:
        f["temp_min_c"] = ov.temp_min_c
    if ov.temp_max_c is not None or ov.temp_min_c is not None:
        f["temp_mean_c"] = (f["temp_max_c"] + f["temp_min_c"]) / 2
        f["hot_day"] = (f["temp_max_c"] >= 36.0).astype(int)
    if ov.weather_type is not None:
        if ov.weather_type not in WEATHER_TYPE_RAIN_LEVEL:
            raise ValueError(f"Unknown weather type '{ov.weather_type}'. Choose one of {sorted(WEATHER_TYPE_RAIN_LEVEL)}")
        f["rain_level"] = WEATHER_TYPE_RAIN_LEVEL[ov.weather_type]
    if ov.weather_type is not None or ov.temp_max_c is not None or ov.temp_min_c is not None:
        f["weather_assumed"] = 0  # the admin gave a forecast, so it is no longer last year's average
    return f


class ForecastService:
    """Loads the final model once and answers forecast questions."""

    def __init__(self, model_dir=FINAL_DIR, history: pd.DataFrame | None = None,
                 detector: SurplusDetector | None = None, recommend_quantile: float = C.RECOMMEND_QUANTILE) -> None:
        self.bundle = ModelBundle.load(model_dir)
        if history is None:
            from feedforward.admin.history import load_combined_history  # simulated history plus real entries
            history = load_combined_history()
        self.history = history
        self.dishes = pd.read_parquet(C.PROCESSED_DIR / "dishes.parquet")
        self.menu = pd.read_parquet(C.PROCESSED_DIR / "weekly_menu.parquet")
        self.detector = detector or StubSurplusDetector()
        self.recommend_quantile = recommend_quantile

    def forecast(self, date, meal_slot: str, dish_ids: list[str] | None = None, overrides: Overrides | None = None,
                 n_samples: int = C.N_SAMPLES) -> dict:
        """Range (P10, P50, P90), recommended quantity, usual plan and surplus risk for each dish of a slot."""
        if meal_slot not in C.MEAL_SLOTS:
            raise ValueError(f"Unknown meal slot '{meal_slot}'. Choose one of {list(C.MEAL_SLOTS)}")
        ov, day = overrides or Overrides(), pd.Timestamp(date).normalize()
        targets = menu_rows_for(pd.DatetimeIndex([day]), self.menu)
        targets = targets[targets["meal_slot"] == meal_slot].reset_index(drop=True)
        if dish_ids is not None:
            targets = targets[targets["dish_id"].isin(dish_ids)].reset_index(drop=True)
        if targets.empty:
            return self._empty(day, meal_slot, ov)
        feats = apply_date_overrides(build_features(targets, self.history, self.dishes), ov)
        expected = self.bundle.att.predict(feats)
        if ov.expected_attendance is not None:
            expected = np.full(len(feats), float(ov.expected_attendance))
        if ov.attendance_change_pct is not None:
            expected = expected * (1 + ov.attendance_change_pct / 100)
        feats["expected_attendance"] = expected
        pred = self.bundle.predict(feats, n_samples=n_samples)
        usual = usual_plan(self.history, targets).to_numpy()
        return self._assemble(day, meal_slot, feats, pred, usual, ov)

    def _assemble(self, day, slot, feats, pred, usual, ov) -> dict:
        """Turn arrays into the response: rounded numbers, risk, totals and notes."""
        q = np.sort(np.stack([pred[0.1], pred[0.5], pred[0.9]]), axis=0)
        rec = round_portions(pred[self.recommend_quantile])
        names = self.dishes.set_index("dish_id")["dish_name"]
        rows = []
        for i, r in feats.reset_index(drop=True).iterrows():
            p10, p50, p90 = (int(round(v)) for v in q[:, i])
            rows.append({"dish_id": r["dish_id"], "dish_name": names.get(r["dish_id"], r["dish_id"]),
                         "is_core": bool(r["is_core"]), "special_limited": bool(r["special_limited"]),
                         "is_choice": bool(r["is_choice"]), "p10": p10, "p50": p50, "p90": p90,
                         "recommended": int(rec[i]), "usual_plan": int(round(usual[i])),
                         "surplus_risk": self.detector.assess(float(usual[i]), p50, p90),
                         "has_history": bool(r["n_lags"] > 0),
                         "last_week_demand": int(round(r["demand_lag_7"])) if r["has_lag_7"] else None,
                         "two_weeks_ago_demand": int(round(r["demand_lag_14"])) if r["has_lag_14"] else None})
        rows.sort(key=lambda d: -d["recommended"])
        total = {k: int(sum(d[k] for d in rows)) for k in ("p10", "p50", "p90", "recommended", "usual_plan")}
        att = int(round(feats["expected_attendance"].iloc[0]))
        return {"date": str(day.date()), "meal_slot": slot, "expected_attendance": att,
                "dishes": rows, "day_facts": self._day_facts(day, feats), "totals": total, "totals_note": TOTALS_NOTE,
                "overrides_applied": ov.applied(), "notes": self._notes(day, rows)}

    @staticmethod
    def _day_facts(day: pd.Timestamp, feats: pd.DataFrame) -> dict:
        """Plain facts about the day that the copilot may quote (all taken from the feature row)."""
        r = feats.iloc[0]
        return {"weekday": day.day_name(), "expected_attendance": int(round(r["expected_attendance"])),
                "attendance_last_week": int(round(r["slot_att_lag_7"])) if r["slot_att_lag_7"] > 0 else None,
                "attendance_two_weeks_ago": int(round(r["slot_att_lag_14"])) if r["slot_att_lag_14"] > 0 else None,
                "exam_week": bool(r["university_exam_any"]), "formative_test": bool(r["formative_test_any"]),
                "holiday": bool(r["tn_public_holiday"] or r["special_declared_holiday"]), "festival": bool(r["major_festival"]),
                "students_mostly_away": bool(r["students_mostly_away"]), "temp_max_c": round(float(r["temp_max_c"]), 1),
                "temp_min_c": round(float(r["temp_min_c"]), 1), "rain_level": int(round(r["rain_level"])),
                "weather_is_assumed": bool(r["weather_assumed"])}

    def _notes(self, day: pd.Timestamp, rows: list[dict]) -> list[str]:
        """Plain language cautions about how far to trust the numbers."""
        notes = []
        ahead = (day - self.history["date"].max()).days
        if ahead > 7:
            notes.append(f"This date is {ahead} days after the last recorded day. Recent history is missing, so "
                         "older weeks are used and the range is less reliable.")
        if any(not d["has_history"] for d in rows):
            notes.append("Some dishes have no history for this weekday yet, so their numbers rely on the dish type only.")
        notes.append("History is simulated on a real menu, calendar and weather. Treat the numbers as estimates.")
        return notes

    def _empty(self, day, slot, ov) -> dict:
        """Response for a slot with no dishes on that day."""
        return {"date": str(day.date()), "meal_slot": slot, "expected_attendance": 0, "dishes": [], "day_facts": {},
                "totals": dict.fromkeys(("p10", "p50", "p90", "recommended", "usual_plan"), 0), "totals_note": "",
                "overrides_applied": ov.applied(), "notes": ["No dishes are on the menu for this slot and day."]}
