"""Forecast versus actual: approved forecast snapshots against the demand the admin logged afterwards."""

import pandas as pd

from feedforward.admin import review_log
from feedforward.admin.store import DATA_SOURCE, LogStore, get_store


def forecast_vs_actual(store: LogStore | None = None) -> dict:
    """One row per dish of a standing approval that now has an actual logged by a person, with a short summary.

    A plan that was sent back or withdrawn after its approval is left out, and so are days the automation filled in
    (they hold the plan itself, not what really happened)."""
    store = store or get_store()
    log = review_log.read_log()
    standing = {k for k, v in review_log.review_index().items() if v["decision"] == "approve"}
    if log.empty or not standing:
        return {"rows": [], "summary": None}
    snap = log[log["decision"] == "approve"].drop_duplicates(["date", "meal_slot", "dish_id"], keep="last")
    snap = snap[[(d, s) in standing for d, s in zip(snap["date"], snap["meal_slot"], strict=True)]]
    kit = store.read("kitchen_log")
    kit = kit[kit["data_source"] == DATA_SOURCE]
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
    for c in ("p10", "p50", "p90", "recommended", "usual_plan", "approved_qty"):
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0).astype(int)
    df["inside_range"] = (df["actual_demand"] >= df["p10"]) & (df["actual_demand"] <= df["p90"])
    df["error_vs_most_likely"] = df["actual_demand"] - df["p50"]
    summary = {"rows": len(df), "inside_range_pct": round(100 * float(df["inside_range"].mean())),
               "mean_abs_error_most_likely": round(float((df["actual_demand"] - df["p50"]).abs().mean())),
               "mean_abs_error_usual_plan": round(float((df["actual_demand"] - df["usual_plan"]).abs().mean()))}
    cols = ["date", "meal_slot", "dish_id", "p10", "p50", "p90", "recommended", "approved_qty", "usual_plan", "actual_demand",
            "inside_range"]
    return {"rows": df[cols].sort_values(["date", "meal_slot", "dish_id"]).to_dict(orient="records"), "summary": summary}
