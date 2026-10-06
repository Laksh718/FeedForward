"""Slot attendance forecaster: how many students will eat in a slot (calendar, weather, recent attendance).

Gradient boosting on log attendance. Training rows get OUT OF FOLD predictions (each block of days is
predicted by a model that never saw that block), so the demand model sees attendance estimates that are as
noisy as the ones it will get at serving time. The spread of the out of fold errors is the uncertainty.
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from feedforward import config as C
from feedforward.data.feature_registry import MEAL_SLOTS

DATE_COLS = ["dow_sin", "dow_cos", "is_weekend", "tn_public_holiday", "major_festival",
             "special_declared_holiday", "compensatory_working_day", "rain_holiday_colleges",
             "days_to_next_holiday", "days_since_last_holiday", "university_exam_any", "formative_test_any",
             "students_mostly_away", "phase_confidence_rank", "temp_max_c", "temp_min_c", "rain_level",
             "senior_classes", "senior_formative", "senior_practical", "senior_theory", "senior_study_gap",
             "senior_away", "senior_enrolment", "first_classes", "first_formative", "first_practical",
             "first_theory", "first_study_gap", "first_away", "first_enrolment"]
ATT_FEATURES = DATE_COLS + [f"slot_{s}" for s in MEAL_SLOTS] + ["slot_att_lag_7", "slot_att_mean3"]
OOF_BLOCKS = 5


def slot_table(panel: pd.DataFrame) -> pd.DataFrame:
    """One row per date and slot (attendance does not depend on the dish)."""
    return panel.drop_duplicates(["date", "meal_slot"]).reset_index(drop=True)


class AttendanceModel:
    """Predicts log attendance for a slot; `sigma` is the out of fold residual spread (log scale)."""

    def __init__(self) -> None:
        self.model = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=300,
                                                   random_state=C.SEED)
        self.sigma = 0.1

    def fit(self, slots: pd.DataFrame) -> "AttendanceModel":
        """Fit on slot rows that have an observed attendance; also sets sigma from out of fold errors."""
        y = np.log(slots["attendance"].to_numpy())
        self.oof_ = self.out_of_fold(slots)
        self.sigma = float(np.std(y - np.log(self.oof_)))
        self.model.fit(slots[ATT_FEATURES], y)
        return self

    def out_of_fold(self, slots: pd.DataFrame) -> np.ndarray:
        """Attendance predicted for each row by a model trained on the other blocks of days."""
        y = np.log(slots["attendance"].to_numpy())
        days = np.sort(slots["date"].unique())
        block_of = {d: i * OOF_BLOCKS // len(days) for i, d in enumerate(days)}
        block = slots["date"].map(block_of).to_numpy()
        out = np.zeros(len(slots))
        for b in range(OOF_BLOCKS):
            m = HistGradientBoostingRegressor(max_depth=4, learning_rate=0.05, max_iter=300, random_state=C.SEED)
            m.fit(slots.loc[block != b, ATT_FEATURES], y[block != b])
            out[block == b] = m.predict(slots.loc[block == b, ATT_FEATURES])
        return np.exp(out)

    def predict(self, df: pd.DataFrame) -> np.ndarray:
        """Expected attendance (people) for rows that have the attendance features."""
        return np.exp(self.model.predict(df[ATT_FEATURES]))


def add_expected_attendance(panel: pd.DataFrame, fit_mask: pd.Series) -> tuple[pd.DataFrame, AttendanceModel]:
    """Add expected_attendance: out of fold for fit rows, model predictions for all other rows."""
    slots = slot_table(panel)
    in_fit = slots["date"].isin(panel.loc[fit_mask, "date"].unique())
    att = AttendanceModel().fit(slots[in_fit])
    expected = pd.Series(att.predict(slots), index=slots.index)
    expected[in_fit] = att.oof_
    table = slots[["date", "meal_slot"]].assign(expected_attendance=expected.to_numpy())
    return panel.merge(table, on=["date", "meal_slot"], how="left"), att
