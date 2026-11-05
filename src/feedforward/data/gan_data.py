"""Training table for the rare event GAN (train period only).

Each row is one dish on one meal slot and date. The GAN learns what demand looks like on rare days
(festival, public holiday, exam week, heavy rain), with some normal days as contrast.
Only things known before the day are used as conditions. Same day consumed, unmet, leftover and
attendance are never inputs. The target is log1p(demand), demand = consumed + unmet.

python -m feedforward.data.gan_data      builds the table and saves the scaler to artifacts/gan/
"""

import json

import joblib
import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from feedforward import config as C
from feedforward.models.attendance import add_expected_attendance

GAN_DIR = C.ARTIFACTS_DIR / "gan"
EVENT_TYPES = ("festival", "holiday", "exam_week", "rain", "normal")
RARE_TYPES = EVENT_TYPES[:-1]
NUMERIC_CONDITIONS = ["rain_level", "log_expected_attendance", "popularity_score"]
MIN_RARE_ROWS = 300       # below this, days next to a rare day are added
NORMAL_PER_RARE = 3       # contrast rows per rare row
LEAKAGE_COLUMNS = {"consumed_qty", "unmet_qty", "leftover_qty", "prepared_qty", "topup_qty", "attendance"}


def event_type(df: pd.DataFrame) -> pd.Series:
    """festival, holiday, exam_week, rain or normal. A later rule wins (a festival beats everything)."""
    out = pd.Series("normal", index=df.index, dtype=object)
    out[df["university_exam_any"] == 1] = "exam_week"
    out[df["rain_level"] >= 2] = "rain"
    out[(df["tn_public_holiday"] == 1) | (df["special_declared_holiday"] == 1)] = "holiday"
    out[df["major_festival"] == 1] = "festival"
    return out


def with_gan_columns(df: pd.DataFrame, dishes: pd.DataFrame) -> pd.DataFrame:
    """Add event_type, category, weekday and log expected attendance (expected_attendance must exist)."""
    out = df.merge(dishes[["dish_id", "category"]], on="dish_id", how="left")
    out["event_type"] = event_type(out)
    out["weekday"] = out["date"].dt.dayofweek
    out["log_expected_attendance"] = np.log(out["expected_attendance"])
    return out


def load_train_panel() -> tuple[pd.DataFrame, pd.DataFrame, object]:
    """Core dish rows of the train period with expected attendance, the dish catalogue and the attendance model."""
    panel = pd.read_parquet(C.TIMESERIES_DIR / "panel.parquet").reset_index(drop=True)
    panel, att = add_expected_attendance(panel, panel["split"] == "train")
    dishes = pd.read_parquet(C.PROCESSED_DIR / "dishes.parquet")
    keep = (panel["split"] == "train") & (panel["is_core"] == 1) & (panel["n_lags"] > 0)
    return with_gan_columns(panel[keep], dishes).reset_index(drop=True), dishes, att


def build_table(seed: int = C.SEED) -> tuple[pd.DataFrame, dict]:
    """Rare rows plus about 3 normal rows per rare row. Returns the table and a log of what was done."""
    train, _, _ = load_train_panel()
    rare = train[train["event_type"] != "normal"]
    log = {"train_rows": len(train), "rare_rows": len(rare), "rare_by_type": rare["event_type"].value_counts().to_dict(),
           "expanded_to_neighbour_days": False}
    pool = train[(train["event_type"] == "normal") & (train["students_mostly_away"] == 0)]
    if len(rare) < MIN_RARE_ROWS:                     # too few: also use the days next to a rare day
        days = pd.DatetimeIndex(rare["date"].unique())
        near = pool["date"].isin(days - pd.Timedelta(days=1)) | pool["date"].isin(days + pd.Timedelta(days=1))
        rare = pd.concat([rare, pool[near]])
        pool = pool[~near]
        log["expanded_to_neighbour_days"] = True
    normal = pool.sample(n=min(len(pool), NORMAL_PER_RARE * len(rare)), random_state=seed)
    table = pd.concat([rare, normal]).sort_values(["date", "meal_slot", "dish_id"]).reset_index(drop=True)
    log["normal_rows"] = len(normal)
    log["table_rows"] = len(table)
    log["last_date"] = str(table["date"].max().date())
    return table, log


class GanScaler:
    """Scales the target and numeric conditions, one hot encodes the categorical ones."""

    def __init__(self) -> None:
        self.num = StandardScaler()
        self.target = StandardScaler()

    def fit(self, table: pd.DataFrame) -> "GanScaler":
        """Learn scales and category lists from the training table."""
        self.categories = {"category": sorted(table["category"].dropna().unique()), "meal_slot": list(C.MEAL_SLOTS),
                           "weekday": list(range(7)), "event_type": list(EVENT_TYPES)}
        self.num.fit(table[NUMERIC_CONDITIONS].to_numpy(dtype=float))
        self.target.fit(np.log1p(table[["demand_qty"]].to_numpy(dtype=float)))
        self.columns = self.condition_names()
        return self

    def condition_names(self) -> list[str]:
        """Names of the condition columns, in the order of conditions()."""
        names = list(NUMERIC_CONDITIONS)
        for key, values in self.categories.items():
            names += [f"{key}={v}" for v in values]
        return names

    def conditions(self, df: pd.DataFrame) -> np.ndarray:
        """Condition matrix (float32): scaled numbers then one hot columns."""
        parts = [self.num.transform(df[NUMERIC_CONDITIONS].to_numpy(dtype=float))]
        for key, values in self.categories.items():
            parts.append(np.stack([(df[key] == v).to_numpy(dtype=float) for v in values], axis=1))
        return np.hstack(parts).astype(np.float32)

    def scale_target(self, demand: np.ndarray) -> np.ndarray:
        """Demand in portions to scaled log1p."""
        return self.target.transform(np.log1p(np.asarray(demand, dtype=float)).reshape(-1, 1)).astype(np.float32)

    def to_demand(self, scaled: np.ndarray) -> np.ndarray:
        """Scaled log1p back to portions (expm1, rounded, never below 0)."""
        log_y = self.target.inverse_transform(np.asarray(scaled, dtype=float).reshape(-1, 1)).ravel()
        return np.clip(np.round(np.expm1(log_y)), 0, None)

    def save(self, folder=GAN_DIR) -> None:
        """Write the scaler and the readable list of condition columns."""
        folder.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, folder / "scaler.joblib")
        (folder / "columns.json").write_text(json.dumps(self.columns, indent=1), encoding="utf-8")

    @staticmethod
    def load(folder=GAN_DIR) -> "GanScaler":
        """Read a saved scaler."""
        return joblib.load(folder / "scaler.joblib")


def main() -> None:
    """Build the table, save the scaler and print the log."""
    table, log = build_table()
    GanScaler().fit(table).save()
    GAN_DIR.mkdir(parents=True, exist_ok=True)
    (GAN_DIR / "table_log.json").write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    print(json.dumps(log, indent=2, default=str))


if __name__ == "__main__":
    main()
