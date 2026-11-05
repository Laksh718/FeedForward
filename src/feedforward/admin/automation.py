"""Automation: approve the coming days and fill the Daily log from approved plans, so nobody has to do it by hand.

Two switches, both off until an admin turns them on in the Daily log:

- auto_approve: every plan from today to `days_ahead - 1` days ahead that nobody has reviewed is approved with the
  recommended quantities (reviewer "Automatic"). A plan a person sent back is left alone: it needs a person.
- auto_log: every day of the last two weeks, up to today, that has approved plans and nothing in the Daily log is
  filled from them: prepared = the approved quantity, eaten = the most likely demand (never more than was
  prepared), the rest left over, attendance = the expected attendance, ingredients from the recipes. These rows are
  marked auto_filled. They show in the Daily log for a person to check and save, and the model does not learn from
  them until then, because they hold the plan rather than what really happened.

run() is called by the server when it starts and every few minutes after that (api.main), and by the Daily log's
Run now button. Running it twice does nothing new: approved plans and filled days are skipped.
"""

import json
import threading
from datetime import date as Date
from datetime import datetime, timedelta

from feedforward import config as C
from feedforward.admin.review_log import AUTOMATIC, append_review, review_index
from feedforward.admin.schemas import AttendanceIn, DaySaveIn, IngredientIn, KitchenRowIn
from feedforward.admin.store import AUTO_SOURCE, LogStore, get_store

DEFAULTS = {"auto_approve": False, "days_ahead": 7, "auto_log": False, "last_run": None}
MAX_DAYS_AHEAD = 14
LOG_BACK_DAYS = 14
APPROVE_NOTE = "Approved automatically with the recommended quantities."
_lock = threading.RLock()


def settings_path():
    """automation.json next to the other admin logs (the folder can be moved with FEEDFORWARD_ADMIN_LOG_DIR)."""
    return C.ADMIN_LOG_DIR / "automation.json"


def load_settings() -> dict:
    """The saved switches, or the defaults (everything off)."""
    path = settings_path()
    saved = {}
    if path.exists():
        try:
            saved = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            saved = {}
    return {**DEFAULTS, **{k: v for k, v in saved.items() if k in DEFAULTS}}


def _write(settings: dict) -> None:
    C.ADMIN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    settings_path().write_text(json.dumps(settings, indent=1), encoding="utf-8")


def save_settings(changes: dict) -> dict:
    """Change some switches and keep the rest. Raises ValueError for a value that makes no sense."""
    with _lock:
        s = load_settings()
        for key in ("auto_approve", "auto_log"):
            if key in changes and changes[key] is not None:
                s[key] = bool(changes[key])
        if changes.get("days_ahead") is not None:
            days = int(changes["days_ahead"])
            if not 1 <= days <= MAX_DAYS_AHEAD:
                raise ValueError(f"Days ahead must be between 1 and {MAX_DAYS_AHEAD}.")
            s["days_ahead"] = days
        _write(s)
        return s


def _approve_ahead(svc, today: Date, days: int) -> tuple[list[dict], list[dict]]:
    """Approve every plan in the window that has no decision. Returns (approved, left for a person)."""
    index = review_index()
    last = Date.fromisoformat(C.FORECAST_LAST_DAY)
    approved, left = [], []
    for i in range(days):
        day = today + timedelta(days=i)
        if day > last:
            break
        for slot in C.MEAL_SLOTS:
            standing = index.get((str(day), slot))
            if standing is None:
                plan = svc.forecast(day, slot)
                if plan["dishes"]:
                    append_review(plan, "approve", AUTOMATIC, APPROVE_NOTE, svc.bundle.info)
                    approved.append({"date": str(day), "meal_slot": slot})
            elif standing["decision"] == "send_back":
                left.append({"date": str(day), "meal_slot": slot})
    return approved, left


def entry_from_plans(svc, day: Date, approvals: dict[str, dict]) -> DaySaveIn:
    """A Daily log entry for one date built from its approved plans ({meal slot: standing approval})."""
    from feedforward.models.forecast_service import Overrides
    from feedforward.models.whatif_impact import ingredient_kg

    attendance, kitchen = [], []
    for slot, review in approvals.items():
        plan = svc.forecast(day, slot, overrides=Overrides(**review.get("overrides", {})))
        wanted = {d["dish_id"]: d["p50"] for d in plan["dishes"]}
        if plan["dishes"]:
            attendance.append(AttendanceIn(meal_slot=slot, attendance=min(C.ENROLLED, max(0, plan["expected_attendance"]))))
        for dish_id, qty in review.get("approved", {}).items():
            want = int(wanted.get(dish_id, qty))
            eaten, short = min(qty, want), max(0, want - qty)
            kitchen.append(KitchenRowIn(meal_slot=slot, dish_id=dish_id, prepared_qty=qty, consumed_qty=eaten,
                                        leftover_qty=qty - eaten, ran_out_early=short > 0, unmet_qty=short or None))
    kg = ingredient_kg([{"dish_id": k.dish_id, "recommended": k.prepared_qty} for k in kitchen])
    ingredients = [IngredientIn(ingredient=name, used_kg=round(v, 1)) for name, v in sorted(kg.items()) if v >= 0.05]
    return DaySaveIn(date=day, entered_by=AUTOMATIC, attendance=attendance, kitchen=kitchen, ingredients=ingredients)


def _log_past(svc, today: Date, store: LogStore) -> list[str]:
    """Fill the Daily log of recent days that have approved plans and no entries. Returns the dates filled."""
    index = review_index()
    have = set(store.read("kitchen_log")["date"].astype(str)) | set(store.read("attendance")["date"].astype(str))
    first = today - timedelta(days=LOG_BACK_DAYS)
    by_date: dict[str, dict[str, dict]] = {}
    for (day, slot), review in index.items():
        if review["decision"] == "approve" and str(first) <= day <= str(today) and day not in have:
            by_date.setdefault(day, {})[slot] = review
    filled = []
    for day in sorted(by_date):
        entry = entry_from_plans(svc, Date.fromisoformat(day), by_date[day])
        if entry.kitchen:
            store.save_day(entry, source=AUTO_SOURCE)
            filled.append(day)
    return filled


def run(svc, today: Date, store: LogStore | None = None) -> dict:
    """Do whatever the switches ask for, once. Returns what was done (also kept as last_run in the settings)."""
    with _lock:
        s = load_settings()
        store = store or get_store()
        approved, left = _approve_ahead(svc, today, s["days_ahead"]) if s["auto_approve"] else ([], [])
        logged = _log_past(svc, today, store) if s["auto_log"] else []
        result = {"at": datetime.now().isoformat(timespec="seconds"), "auto_approve": s["auto_approve"],
                  "auto_log": s["auto_log"], "approved": approved, "logged_dates": logged, "left_for_a_person": left}
        _last_check["at"] = result["at"]
        if approved or logged:   # written only when something was done, so open pages reload only then
            s["last_run"] = {k: result[k] for k in ("at", "logged_dates")} | {
                "approved_count": len(approved), "left_for_a_person_count": len(left)}
            _write(s)
        return result


_last_check: dict = {"at": None}


def status() -> dict:
    """The switches, the last run that did something, and when the server last checked."""
    return {**load_settings(), "last_check": _last_check["at"], "max_days_ahead": MAX_DAYS_AHEAD}
