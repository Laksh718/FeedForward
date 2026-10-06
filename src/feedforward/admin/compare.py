"""Forecast versus actual: approved forecast snapshots against the demand the admin logged afterwards."""

import pandas as pd

from feedforward.admin import review_log
from feedforward.admin.store import LogStore, get_store


def forecast_vs_actual(store: LogStore | None = None) -> dict:
    """One row per approved snapshot dish that now has a logged actual, with a short summary."""
    store = store or get_store()
    if not review_log.LOG_PATH.exists():
        return {"rows": [], "summary": None}
    snap = pd.read_csv(review_log.LOG_PATH, encoding="utf-8", keep_default_na=False)
    snap = snap[snap["decision"] == "approve"].sort_values("reviewed_at").drop_duplicates(["date", "meal_slot", "dish_id"], keep="last")
    kit = store.read("kitchen_log")
    if snap.empty or kit.empty:
        return {"rows": [], "summary": None}
    for c in ("prepared_qty", "topup_qty", "unmet_qty"):
        kit[c] = pd.to_numeric(kit[c], errors="coerce").fillna(0)
    supply = kit["prepared_qty"] + kit["topup_qty"]
    cons, left = pd.to_numeric(kit["consumed_qty"], errors="coerce"), pd.to_numeric(kit["leftover_qty"], errors="coerce")
    kit["actual_demand"] = (cons.fillna(supply - left) + kit["unmet_qty"]).astype(int)
    df = snap.merge(kit[["date", "meal_slot", "dish_id", "actual_demand"]], on=["date", "meal_slot", "dish_id"])
    if df.empty:
        return {"rows": [], "summary": None}
    for c in ("p10", "p50", "p90", "recommended", "usual_plan"):
        df[c] = pd.to_numeric(df[c])
    df["inside_range"] = (df["actual_demand"] >= df["p10"]) & (df["actual_demand"] <= df["p90"])
    df["error_vs_most_likely"] = df["actual_demand"] - df["p50"]
    summary = {"rows": len(df), "inside_range_pct": round(100 * float(df["inside_range"].mean())),
               "mean_abs_error_most_likely": round(float((df["actual_demand"] - df["p50"]).abs().mean())),
               "mean_abs_error_usual_plan": round(float((df["actual_demand"] - df["usual_plan"]).abs().mean()))}
    cols = ["date", "meal_slot", "dish_id", "p10", "p50", "p90", "recommended", "usual_plan", "actual_demand", "inside_range"]
    return {"rows": df[cols].sort_values(["date", "meal_slot", "dish_id"]).to_dict(orient="records"), "summary": summary}
