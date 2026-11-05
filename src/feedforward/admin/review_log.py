"""Review log: every Approve, Send back or Withdraw is stored with a snapshot of the forecast the reviewer saw.

The snapshot lets the dashboard later compare what was forecast with what actually happened (M7).
Stored in data_store/admin_logs/forecast_log.csv (git ignored, real entries).

Decisions: "approve" (cook the approved quantities), "send_back" (a person must look at it again) and "withdraw"
(the earlier decision no longer stands, so the plan is waiting for a review again).
"""

import json
import threading
from datetime import datetime

import pandas as pd

from feedforward import config as C

LOG_PATH = C.ADMIN_LOG_DIR / "forecast_log.csv"
COLUMNS = ["reviewed_at", "date", "meal_slot", "decision", "reviewer", "note", "dish_id", "p10", "p50", "p90",
           "recommended", "approved_qty", "usual_plan", "surplus_risk", "overrides", "model_trained_to", "data_source"]
DECISIONS = ("approve", "send_back", "withdraw")
AUTOMATIC = "Automatic"          # reviewer name of decisions made by the automation (feedforward.admin.automation)
_lock = threading.Lock()
_cache: dict = {"key": None, "log": None, "latest": None}


def append_review(plan: dict, decision: str, reviewer: str | None, note: str | None, model_info: dict,
                  adjusted: dict[str, int] | None = None) -> int:
    """Write one row per dish of the plan that was reviewed. Returns the number of rows written.

    approved_qty is what the reviewer approved: the recommendation unless they changed the quantity.
    """
    if decision not in DECISIONS:
        raise ValueError(f"Unknown decision '{decision}'. Choose one of {list(DECISIONS)}.")
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


def read_log() -> pd.DataFrame:
    """Every review row, oldest first (read again only when the file changes)."""
    path = LOG_PATH
    if not path.exists():
        return pd.DataFrame(columns=COLUMNS)
    stat = path.stat()
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    with _lock:
        if _cache["key"] != key:
            log = pd.read_csv(path, encoding="utf-8", keep_default_na=False, dtype=str)
            _cache.update(key=key, log=log.sort_values("reviewed_at", kind="stable").reset_index(drop=True), latest=None)
        return _cache["log"]


def _core_ids() -> set[str] | None:
    try:
        dishes = pd.read_parquet(C.PROCESSED_DIR / "dishes.parquet")
    except FileNotFoundError:
        return None
    return set(dishes.loc[dishes["forecast_priority"] == "core", "dish_id"])


def _summary(rows: pd.DataFrame, core_ids: set[str] | None) -> dict:
    """One review (all its dish rows) as the dashboard shows it."""
    first = rows.iloc[0]
    out = {"decision": first["decision"], "reviewed_at": first["reviewed_at"], "reviewer": first["reviewer"],
           "note": first["note"], "automatic": first["reviewer"] == AUTOMATIC,
           "overrides": json.loads(first["overrides"] or "{}")}
    if first["decision"] == "approve":
        qty = pd.to_numeric(rows["approved_qty"], errors="coerce").fillna(0).astype(int)
        rec = pd.to_numeric(rows["recommended"], errors="coerce").fillna(0).astype(int)
        core = rows["dish_id"].isin(core_ids) if core_ids is not None else pd.Series(True, index=rows.index)
        out.update(approved_total=int(qty[core].sum()), approved_total_all=int(qty.sum()),
                   edited_dishes=int((qty != rec).sum()),
                   approved={d: int(q) for d, q in zip(rows["dish_id"], qty, strict=True)})
    return out


def review_index() -> dict[tuple[str, str], dict]:
    """The standing decision of every (date, meal slot) that has one. A withdrawn decision leaves the plan out."""
    log = read_log()
    with _lock:
        if _cache["latest"] is not None and _cache["log"] is log:
            return _cache["latest"]
    out: dict[tuple[str, str], dict] = {}
    if not log.empty:
        core = _core_ids()
        newest = log.groupby(["date", "meal_slot"])["reviewed_at"].transform("max") == log["reviewed_at"]
        for (date, slot), rows in log[newest].groupby(["date", "meal_slot"]):
            rows = rows[rows["decision"] == rows["decision"].iloc[-1]].drop_duplicates("dish_id", keep="last")
            if rows["decision"].iloc[0] != "withdraw":
                out[(date, slot)] = _summary(rows, core)
    with _lock:
        if _cache["log"] is log:
            _cache["latest"] = out
    return out


def latest_review(date: str, meal_slot: str) -> dict | None:
    """The standing decision for a date and slot, or None if nobody has reviewed it (or it was withdrawn)."""
    return review_index().get((str(date), meal_slot))


def review_events(limit: int = 50) -> list[dict]:
    """The most recent decisions, newest first: one entry per plan reviewed (not per dish)."""
    log = read_log()
    if log.empty:
        return []
    heads = log.drop_duplicates(["reviewed_at", "date", "meal_slot", "decision"], keep="first")
    heads = heads.iloc[::-1].sort_values("reviewed_at", ascending=False, kind="stable").head(limit)   # newest written first
    return [{"at": r["reviewed_at"], "date": r["date"], "meal_slot": r["meal_slot"], "decision": r["decision"],
             "reviewer": r["reviewer"], "note": r["note"], "automatic": r["reviewer"] == AUTOMATIC}
            for _, r in heads.iterrows()]
