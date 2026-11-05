"""What happened lately, newest first: plan decisions, Daily log saves and automatic runs, for every page to show.

version() changes whenever anything in the admin log folder is written, so an open dashboard can ask for it every
few seconds and reload only when something really changed (a review from another tab, an automatic run, a save).
"""

import pandas as pd

from feedforward import config as C
from feedforward.admin import automation, review_log
from feedforward.admin.store import AUTO_SOURCE, TABLES, LogStore, get_store


def version() -> str:
    """A short token that changes whenever a file in the admin log folder changes."""
    folder = C.ADMIN_LOG_DIR
    if not folder.exists():
        return "0"
    stats = [p.stat() for p in folder.iterdir() if p.is_file() and p.suffix in (".csv", ".json")]
    return f"{max((s.st_mtime_ns for s in stats), default=0)}-{sum(s.st_size for s in stats)}"


def log_events(store: LogStore | None = None, limit: int = 50) -> list[dict]:
    """One event per Daily log save: the date saved, when, by whom, and how many rows of each table."""
    store = store or get_store()
    frames = [store.read(t)[["date", "entered_at", "entered_by", "data_source"]].assign(table=t) for t in TABLES]
    rows = pd.concat([f for f in frames if not f.empty], ignore_index=True) if any(not f.empty for f in frames) else None
    if rows is None:
        return []
    out = []
    for (date, at, by, source), g in rows.groupby(["date", "entered_at", "entered_by", "data_source"]):
        out.append({"at": at, "kind": "log_auto" if source == AUTO_SOURCE else "log", "date": date, "by": by,
                    "rows": {t: int((g["table"] == t).sum()) for t in TABLES}})
    return sorted(out, key=lambda e: e["at"], reverse=True)[:limit]


def recent(limit: int = 20, store: LogStore | None = None) -> dict:
    """The newest decisions, log saves and automatic runs together, plus the current version token."""
    events = [{"kind": e["decision"], **{k: e[k] for k in ("at", "date", "meal_slot", "reviewer", "note", "automatic")}}
              for e in review_log.review_events(limit)]
    events += log_events(store, limit)
    run = automation.load_settings().get("last_run")
    if run:
        events.append({"kind": "automation", "at": run["at"], "approved_count": run.get("approved_count", 0),
                       "logged_dates": run.get("logged_dates", []), "left_for_a_person_count": run.get("left_for_a_person_count", 0)})
    events.sort(key=lambda e: e["at"], reverse=True)
    return {"version": version(), "events": events[:limit]}
