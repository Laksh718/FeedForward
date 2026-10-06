"""Clean kitchen_history_raw.csv. The clean file is used only as ground truth to test this.

Steps (each one is counted in the cleaning log):
1. drop exact duplicate rows
2. normalise dish names with the text pipeline and map them to the catalogue
3. repair missing attendance and students_present from other rows of the same date and slot
4. recompute missing or negative leftover_qty as prepared + topup - consumed
5. recompute leftover_kg from portion size when leftover_qty was repaired
6. check consistency and flag outliers (never silently removed)
"""

import json

import pandas as pd

from feedforward import config as C
from feedforward.data.loaders import load_table
from feedforward.data.nlp_text import display_name, fuzzy_match
from feedforward.data.preprocess import dish_catalogue, normalise_ids

OUTLIER_Z = 4.0  # robust z score (median and MAD) above which a quantity is flagged


def _fill_group_value(df: pd.DataFrame, col: str, keys: list[str]) -> int:
    """Fill missing values of col with the value other rows of the same group share."""
    before = int(df[col].isna().sum())
    df[col] = df[col].fillna(df.groupby(keys)[col].transform("max"))
    return before - int(df[col].isna().sum())


def flag_outliers(df: pd.DataFrame) -> pd.Series:
    """Flag unusual demand per attendee for a dish and slot (robust z score; flag only, never drop)."""
    demand = (df["consumed_qty"] + df["unmet_qty"]) / df["attendance"]  # per attendee, so crowds do not count
    grp = demand.groupby([df["meal_slot"], df["dish_id"]])
    med = grp.transform("median")
    mad = (demand - med).abs().groupby([df["meal_slot"], df["dish_id"]]).transform("median")
    z = 0.6745 * (demand - med) / mad.where(mad > 0)
    return (z.abs() > OUTLIER_Z).fillna(False)


def clean_kitchen(raw: pd.DataFrame, dishes: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Return the cleaned table and a log of how many rows each step touched."""
    log: dict[str, int] = {"rows_in": len(raw)}
    df = raw.drop_duplicates().copy()
    log["duplicates_dropped"] = len(raw) - len(df)

    catalogue = dish_catalogue(dishes)
    names = df["dish_name"].map(lambda n: fuzzy_match(n, catalogue))
    log["dish_names_changed"] = int((df["dish_name"] != df["dish_name"].map(display_name)).sum())
    log["dish_names_needing_review"] = int(sum(n.needs_review for n in names))
    df["dish_id"] = [n.match if n.match else d for n, d in zip(names, df["dish_id"].str.upper(), strict=True)]
    names_by_id = dishes.set_index("dish_id")["dish_name"]
    df["dish_name"] = df["dish_id"].map(names_by_id)

    log["attendance_repaired"] = _fill_group_value(df, "attendance", ["date", "meal_slot"])
    log["students_present_repaired"] = _fill_group_value(df, "students_present", ["date"])

    left = df["prepared_qty"] + df["topup_qty"] - df["consumed_qty"]
    bad = df["leftover_qty"].isna() | (df["leftover_qty"] < 0)
    log["leftover_missing"] = int(df["leftover_qty"].isna().sum())
    log["leftover_negative"] = int((df["leftover_qty"] < 0).sum())
    df.loc[bad, "leftover_qty"] = left[bad]
    kg_per_portion = df["dish_id"].map(dishes.set_index("dish_id")["portion_g"]) / 1000
    df.loc[bad, "leftover_kg"] = (df.loc[bad, "leftover_qty"] * kg_per_portion[bad]).round(2)

    for col in ("students_present", "attendance", "leftover_qty"):
        df[col] = df[col].astype(int)
    log["consistency_violations"] = int((left != df["leftover_qty"]).sum())
    df["demand_outlier"] = flag_outliers(df)
    log["demand_outliers_flagged"] = int(df["demand_outlier"].sum())
    log["rows_out"] = len(df)
    return df.sort_values(["date", "meal_slot", "dish_id"]).reset_index(drop=True), log


def compare_with_truth(clean: pd.DataFrame, truth: pd.DataFrame) -> dict:
    """Compare the cleaned table with kitchen_history.csv column by column."""
    keys = ["date", "meal_slot", "dish_id"]
    a = clean.drop(columns="demand_outlier").sort_values(keys).reset_index(drop=True)
    b = truth.sort_values(keys).reset_index(drop=True)
    result = {"same_row_count": len(a) == len(b)}
    if not result["same_row_count"]:
        return result
    diffs = {c: int((a[c] != b[c]).sum()) for c in b.columns if (a[c] != b[c]).any()}
    result["columns_with_differences"] = diffs
    return result


def main() -> None:
    """Clean the raw file, save it with the log and print the ground truth comparison."""
    dishes = normalise_ids(load_table("dishes"))
    clean, log = clean_kitchen(load_table("kitchen_history_raw"), dishes)
    log["ground_truth_comparison"] = compare_with_truth(clean, load_table("kitchen_history"))
    C.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    clean.to_parquet(C.PROCESSED_DIR / "kitchen_clean.parquet", index=False)
    C.REPORTS_DIR.mkdir(exist_ok=True)
    (C.REPORTS_DIR / "cleaning_log.json").write_text(json.dumps(log, indent=2, default=str), encoding="utf-8")
    print(json.dumps(log, indent=2, default=str))


if __name__ == "__main__":
    main()
