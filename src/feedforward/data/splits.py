"""Chronological splits, rolling origin folds and regimes. Rows are never shuffled."""

import pandas as pd

from feedforward import config as C

REGIMES = ("normal", "exam", "holiday_festival", "vacation", "rainy")


def assign_split(dates: pd.Series) -> pd.Series:
    """Label each date train, val or test by the fixed cut dates in config."""
    out = pd.Series("train", index=dates.index)
    out[(dates >= C.VAL_START) & (dates <= C.VAL_END)] = "val"
    out[(dates >= C.TEST_START) & (dates <= C.TEST_END)] = "test"
    return out


def rolling_origin_folds(n_folds: int = C.N_FOLDS, days: int = C.FOLD_DAYS) -> list[dict]:
    """Expanding window folds: train on everything before each block of `days` days."""
    end = pd.Timestamp(C.HISTORY_END)
    first = end - pd.Timedelta(days=n_folds * days - 1)
    folds = []
    for k in range(n_folds):
        start = first + pd.Timedelta(days=k * days)
        stop = start + pd.Timedelta(days=days - 1)
        folds.append({"fold": k + 1, "train_end": start - pd.Timedelta(days=1), "test_start": start,
                      "test_end": stop})
    return folds


def regime(df: pd.DataFrame) -> pd.Series:
    """Label each row by the situation it is in. Later rules override earlier ones (vacation beats everything)."""
    out = pd.Series("normal", index=df.index)
    out[df["rain_level"] >= 2] = "rainy"
    out[df["university_exam_any"] == 1] = "exam"  # formative test weeks are normal class days
    out[(df["tn_public_holiday"] == 1) | (df["major_festival"] == 1)
        | (df["special_declared_holiday"] == 1)] = "holiday_festival"
    out[df["students_mostly_away"] == 1] = "vacation"
    return out
