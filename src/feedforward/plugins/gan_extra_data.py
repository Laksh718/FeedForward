"""Plug in point for the GAN rare event generator (teammate).

The GAN should produce synthetic rows with the same columns as artifacts/timeseries/panel.parquet plus
expected_attendance, saved as parquet or csv. Train with:  python -m feedforward.models.train --extra-data FILE
Synthetic rows are down weighted and are never used for validation, testing or calibration.
"""

from pathlib import Path

import pandas as pd

from feedforward import config as C
from feedforward.data.feature_registry import FEATURE_COLUMNS

REQUIRED_COLUMNS = ["date", "meal_slot", "dish_id", "dish_idx", "is_core", "demand_qty", "expected_attendance",
                    *FEATURE_COLUMNS]


def load_extra_rows(path: Path) -> pd.DataFrame:
    """Read and validate synthetic rows. Raises ValueError if a column is missing or a value is invalid."""
    path = Path(path)
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, parse_dates=["date"])
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    if df[REQUIRED_COLUMNS].isna().any().any() or (df["demand_qty"] < 0).any():
        raise ValueError(f"{path.name}: NaN or negative demand in synthetic rows")
    return df.assign(is_synthetic=True, sample_weight=C.EXTRA_DATA_WEIGHT)
