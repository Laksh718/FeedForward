"""Real entries as history rows (same columns as kitchen_history.csv) and the combined history used for forecasting
and retraining. The data_source column keeps simulated and real rows apart. Days the automation filled from the
approved plan (auto_filled) are left out until a person checks and saves them: they hold the plan, not what happened."""

import pandas as pd

from feedforward import config as C
from feedforward.admin.store import DATA_SOURCE, LogStore, get_store
from feedforward.data.features import menu_rows_for

SIMULATED = "history_simulated"


def admin_history_rows(store: LogStore | None = None) -> tuple[pd.DataFrame, int]:
    """Real kitchen rows in the history format. Returns (rows, number of rows skipped for lack of an attendance number)."""
    store = store or get_store()
    kit, att = store.read("kitchen_log"), store.read("attendance")
    kit, att = kit[kit["data_source"] == DATA_SOURCE], att[att["data_source"] == DATA_SOURCE]   # not the automatic fills
    if kit.empty:
        return pd.DataFrame(), 0
    dishes = pd.read_parquet(C.PROCESSED_DIR / "dishes.parquet").set_index("dish_id")
    clean = pd.read_parquet(C.PROCESSED_DIR / "kitchen_clean.parquet")
    limited = clean.groupby("dish_id")["special_limited"].max()
    menu = pd.read_parquet(C.PROCESSED_DIR / "weekly_menu.parquet")
    df = kit.merge(att[["date", "meal_slot", "attendance", "students_present"]], on=["date", "meal_slot"], how="left")
    skipped = int((df["attendance"] == "").sum() | df["attendance"].isna().sum())
    df = df[df["attendance"].notna() & (df["attendance"] != "")].copy()
    if df.empty:
        return pd.DataFrame(), skipped
    for col in ("prepared_qty", "topup_qty", "attendance", "unmet_qty"):
        df[col] = pd.to_numeric(df[col]).astype(int)
    supply = df["prepared_qty"] + df["topup_qty"]
    cons, left = pd.to_numeric(df["consumed_qty"], errors="coerce"), pd.to_numeric(df["leftover_qty"], errors="coerce")
    df["consumed_qty"] = cons.fillna(supply - left).astype(int)
    df["leftover_qty"] = left.fillna(supply - cons).astype(int)
    df["date"] = pd.to_datetime(df["date"])
    present = pd.to_numeric(df["students_present"], errors="coerce")
    df["students_present"] = present.fillna(df.groupby("date")["attendance"].transform("max")).astype(int)
    meta = dishes.loc[df["dish_id"], ["dish_name", "category", "forecast_priority", "diet", "portion_g"]].reset_index(drop=True)
    df = pd.concat([df.reset_index(drop=True), meta], axis=1)
    df["leftover_kg"] = (df["leftover_qty"] * df["portion_g"] / 1000).round(2)
    df["special_limited"] = df["dish_id"].map(limited).fillna(0).astype(int)
    choice = menu_rows_for(pd.DatetimeIndex(sorted(df["date"].unique())), menu)[["date", "meal_slot", "dish_id", "is_choice", "n_options"]]
    df = df.merge(choice, on=["date", "meal_slot", "dish_id"], how="left")
    df[["is_choice", "n_options"]] = df[["is_choice", "n_options"]].fillna({"is_choice": 0, "n_options": 1}).astype(int)
    df["enrolled"] = C.ENROLLED
    df["data_source"] = DATA_SOURCE
    cols = [c for c in clean.columns if c in df.columns] + ["data_source"]
    return df[cols], skipped


def load_combined_history(store: LogStore | None = None) -> pd.DataFrame:
    """Cleaned simulated history plus real rows, newest real entry winning when a key appears twice."""
    clean = pd.read_parquet(C.PROCESSED_DIR / "kitchen_clean.parquet").assign(data_source=SIMULATED)
    real, _ = admin_history_rows(store)
    if real.empty:
        return clean
    key = ["date", "meal_slot", "dish_id"]
    both = pd.concat([clean, real[[c for c in clean.columns if c in real.columns]]], ignore_index=True)
    return both.drop_duplicates(key, keep="last").sort_values(key).reset_index(drop=True)


def real_day_count(store: LogStore | None = None) -> int:
    """Number of distinct dates with usable real kitchen rows."""
    rows, _ = admin_history_rows(store)
    return 0 if rows.empty else int(rows["date"].nunique())
