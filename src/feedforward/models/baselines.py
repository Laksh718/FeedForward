"""Baselines the VAE must beat, and the simple rule used for support dishes.

Point baselines: same weekday last week, mean of the last 3 same weekdays, the manager's usual plan.
Strong non generative baseline: gradient boosting quantile regression (alpha 0.1, 0.5, 0.9).
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

from feedforward import config as C
from feedforward.models.prep import FeatureTransformer

QUANTILES = (0.1, 0.5, 0.9)


def usual_plan(history: pd.DataFrame, targets: pd.DataFrame) -> pd.Series:
    """Manager rule: average of the same dish, slot and weekday over the last two weeks, plus 12 percent.

    Uses what the manager sees (consumed portions). If only one of the two weeks exists, that one is used.
    Dishes with no history in those weeks get 0 (the dashboard shows this as "no usual plan").
    """
    key = ["date", "meal_slot", "dish_id"]
    out = targets[key].copy()
    for week in range(1, C.USUAL_PLAN_WEEKS + 1):
        past = history[key + ["consumed_qty"]].copy()
        past["date"] = past["date"] + pd.Timedelta(days=7 * week)
        out = out.merge(past.rename(columns={"consumed_qty": f"w{week}"}), on=key, how="left")
    mean = out[[f"w{w}" for w in range(1, C.USUAL_PLAN_WEEKS + 1)]].mean(axis=1).fillna(0)
    return pd.Series((mean * (1 + C.USUAL_PLAN_BUFFER)).to_numpy(), index=targets.index)


def last_week(df: pd.DataFrame) -> np.ndarray:
    """Demand on the same weekday last week (the mean of other lags if the dish was not served)."""
    return df["demand_lag_7"].to_numpy()


def mean_last_three(df: pd.DataFrame) -> np.ndarray:
    """Mean demand of the last 3 same weekdays."""
    return df["demand_mean3"].to_numpy()


class GBMQuantile:
    """Three gradient boosting models, one per quantile, trained on log1p demand."""

    def __init__(self) -> None:
        self.tf = FeatureTransformer()
        self.models = {q: HistGradientBoostingRegressor(loss="quantile", quantile=q, max_depth=5,
                                                        learning_rate=0.05, max_iter=300, random_state=C.SEED)
                       for q in QUANTILES}

    def fit(self, df: pd.DataFrame) -> "GBMQuantile":
        """Fit on core dish rows (needs expected_attendance and demand_qty columns)."""
        x, y = self.tf.fit(df).transform(df), np.log1p(df["demand_qty"].to_numpy())
        for model in self.models.values():
            model.fit(x, y)
        return self

    def predict(self, df: pd.DataFrame) -> dict[float, np.ndarray]:
        """Quantile forecasts in portions; quantiles are sorted so P10 <= P50 <= P90."""
        x = self.tf.transform(df)
        raw = np.sort(np.stack([self.models[q].predict(x) for q in QUANTILES]), axis=0)
        return {q: np.clip(np.expm1(raw[i]), 0, None) for i, q in enumerate(QUANTILES)}


class SupportRule:
    """Support dishes (bread, butter, chutney ...): demand = recent rate per attendee x expected attendance.

    The spread comes from how far the rule was off on training rows, as ratios of actual to rule.
    """

    def __init__(self) -> None:
        self.ratios: dict[float, float] = {}
        self.slot_rate: dict[str, float] = {}

    def _base(self, df: pd.DataFrame) -> np.ndarray:
        rate = df["rate_mean3"].where(df["n_lags"] > 0, df["meal_slot"].map(self.slot_rate))
        return (rate * df["expected_attendance"]).to_numpy()

    def fit(self, df: pd.DataFrame) -> "SupportRule":
        """Learn the typical rate per slot (for dishes with no history) and the quantiles of actual / rule."""
        self.slot_rate = (df["demand_qty"] / df["attendance"]).groupby(df["meal_slot"]).median().to_dict()
        base = self._base(df)
        ok = (base > 0) & (df["n_lags"] > 0).to_numpy()
        ratio = df["demand_qty"].to_numpy()[ok] / base[ok]
        self.ratios = {q: float(np.quantile(ratio, q)) for q in (0.1, 0.25, 0.5, 0.75, 0.9)}
        return self

    def predict(self, df: pd.DataFrame) -> dict[float, np.ndarray]:
        """Quantile forecasts in portions for support dishes."""
        base = self._base(df)
        return {q: base * r for q, r in self.ratios.items()}
