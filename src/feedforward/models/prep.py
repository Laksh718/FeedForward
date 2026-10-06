"""Turn feature tables into the numeric matrices the models use (fit on training rows only)."""

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from feedforward.data.feature_registry import FEATURE_COLUMNS, PHASE_GROUPS
from feedforward.data.features import add_weather_noise

WEATHER_COLS = ["temp_max_c", "temp_min_c", "temp_mean_c", "rain_level", "hot_day"]
LOG_COLS = [f"demand_lag_{n}" for n in (7, 14, 21)] + ["demand_mean3", "demand_std3"] + \
           [f"slot_att_lag_{n}" for n in (7, 14, 21)] + ["slot_att_mean3"]
# Month is left out of the models: the data covers one year, so no month is seen twice and a network can only
# memorise it. Unseen months at test time (July, August) then push predictions off. See docs/decisions.md.
PHASE_ONE_HOTS = [f"{c}_{g}" for c in ("senior", "first") for g in PHASE_GROUPS]
NOT_MODEL_INPUTS = ["month_sin", "month_cos"] + PHASE_ONE_HOTS
INPUT_COLUMNS = [c for c in FEATURE_COLUMNS if c not in NOT_MODEL_INPUTS] + ["log_expected_attendance"]


def with_log_attendance(df: pd.DataFrame) -> pd.DataFrame:
    """Add log expected attendance (column expected_attendance must exist)."""
    return df.assign(log_expected_attendance=np.log1p(df["expected_attendance"]))


def noisy_weather_rows(df: pd.DataFrame, rng: np.random.Generator) -> pd.DataFrame:
    """Training only: one forecast error per date (all dishes of a day share the same weather forecast)."""
    days = df.drop_duplicates("date")[["date", *WEATHER_COLS]]
    noisy = add_weather_noise(days, rng).set_index("date")
    out = df.copy()
    out[WEATHER_COLS] = noisy.loc[out["date"], WEATHER_COLS].to_numpy()
    return out


class FeatureTransformer:
    """Log transform of count columns, then standardise. Fitted once on training rows."""

    def __init__(self) -> None:
        self.scaler = StandardScaler()

    @staticmethod
    def _raw(df: pd.DataFrame) -> np.ndarray:
        x = with_log_attendance(df)[INPUT_COLUMNS].copy()
        x[LOG_COLS] = np.log1p(x[LOG_COLS])
        x["demand_trend"] = np.sign(x["demand_trend"]) * np.log1p(x["demand_trend"].abs())
        return x.to_numpy(dtype=np.float64)

    def fit(self, df: pd.DataFrame) -> "FeatureTransformer":
        """Learn means and spreads from training rows."""
        self.scaler.fit(self._raw(df))
        return self

    def transform(self, df: pd.DataFrame) -> np.ndarray:
        """Scaled float32 matrix, one row per input row."""
        return self.scaler.transform(self._raw(df)).astype(np.float32)
