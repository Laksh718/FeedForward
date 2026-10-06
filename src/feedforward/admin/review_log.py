"""Review log: every Approve or Send back is stored with a snapshot of the forecast the reviewer saw.

The snapshot lets the dashboard later compare what was forecast with what actually happened (M7).
Stored in data_store/admin_logs/forecast_log.csv (git ignored, real entries).
"""

import json
import threading
from datetime import datetime

import pandas as pd

from feedforward import config as C

LOG_PATH = C.ADMIN_LOG_DIR / "forecast_log.csv"
COLUMNS = ["reviewed_at", "date", "meal_slot", "decision", "reviewer", "note", "dish_id", "p10", "p50", "p90",
           "recommended", "approved_qty", "usual_plan", "surplus_risk", "overrides", "model_trained_to", "data_source"]
_lock = threading.Lock()


def append_review(plan: dict, decision: str, reviewer: str | None, note: str | None, model_info: dict,
                  adjusted: dict[str, int] | None = None) -> int:
    """Write one row per dish of the plan that was reviewed. Returns the number of rows written.

    approved_qty is what the reviewer approved: the recommendation unless they changed the quantity.
    """
    adjusted = adjusted or {}
    now = datetime.now().isoformat(timespec="seconds")
    rows = [{"reviewed_at": now, "date": plan["date"], "meal_slot": plan["meal_slot"], "decision": decision,
             "reviewer": reviewer or "", "note": note or "", "dish_id": d["dish_id"], "p10": d["p10"], "p50": d["p50"],
             "p90": d["p90"], "recommended": d["recommended"],
             "approved_qty": adjusted.get(d["dish_id"], d["recommended"]) if decision == "approve" else "",
             "usual_plan": d["usual_plan"],
             "surplus_risk": d["surplus_risk"], "overrides": json.dumps(plan["overrides_applied"]),
             "model_trained_to": model_info.get("train_end", ""), "data_source": "model_snapshot"}
            for d in plan["dishes"]]
    if not rows:
        return 0
    with _lock:
        C.ADMIN_LOG_DIR.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows, columns=COLUMNS).to_csv(LOG_PATH, mode="a", header=not LOG_PATH.exists(), index=False,
                                                   encoding="utf-8")
    return len(rows)


def latest_review(date: str, meal_slot: str) -> dict | None:
    """The most recent decision for a date and slot, or None if nobody has reviewed it yet."""
    if not LOG_PATH.exists():
        return None
    log = pd.read_csv(LOG_PATH, encoding="utf-8", keep_default_na=False)
    hit = log[(log["date"] == date) & (log["meal_slot"] == meal_slot)]
    if hit.empty:
        return None
    last = hit.sort_values("reviewed_at").iloc[-1]
    return {"decision": last["decision"], "reviewed_at": last["reviewed_at"], "reviewer": last["reviewer"],
            "note": last["note"]}
