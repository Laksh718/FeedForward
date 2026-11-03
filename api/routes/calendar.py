"""GET /api/calendar: a month at a time, the project's own calendar (real Tamil Nadu public holidays,
festivals and exam phases, see feedforward.data.calendar_future) cross-checked against a live public
holiday calendar so the dashboard can show "confirmed online" next to a date.

The live check is best effort: date.nager.at is a free, no-key public holiday API. If it cannot be
reached (offline, blocked, rate limited) the month still renders from the project's own data, with
`live_source: "offline"`.
"""

import re
import time
from datetime import date as Date

import httpx
import pandas as pd
from fastapi import APIRouter

from feedforward import config as C
from feedforward.admin.context import overlay_calendar

router = APIRouter()

# A blanket note the seeded future calendar puts on every single row (data provenance, not a per-day event);
# showing it as if it were the day's event would flag almost every future date for no real reason.
BOILERPLATE_NOTE_PREFIX = "Future date, seeded from"

DISPLAY_COLS = ["date", "day_of_week", "is_weekend", "holiday_name", "tn_public_holiday", "major_festival",
                "special_declared_holiday", "rain_holiday_colleges", "university_exam_any", "formative_test_any",
                "students_mostly_away", "event_note", "senior_phase"]

# Google's public "Holidays in India" calendar: no key needed, covers the whole year range we show.
LIVE_CALENDAR_URL = ("https://calendar.google.com/calendar/ical/en.indian%23holiday%40group.v.calendar.google.com"
                      "/public/basic.ics")
LIVE_EVENT = re.compile(r"DTSTART;VALUE=DATE:(\d{8}).*?SUMMARY:(.*?)\r?\n", re.S)
_LIVE_TTL_S = 24 * 3600
_live_cache: tuple[float, dict[str, str]] | None = None   # (fetched_at, {iso_date: holiday name})


def _combined_calendar() -> pd.DataFrame:
    """The real calendar followed by the seeded future calendar, admin overlays applied, one row per day."""
    hist = pd.read_parquet(C.PROCESSED_DIR / "calendar.parquet")
    fut = pd.read_csv(C.CALENDAR_FUTURE_CSV, parse_dates=["date"], encoding="utf-8")
    cols = [c for c in DISPLAY_COLS if c in hist.columns and c in fut.columns]
    cal = pd.concat([hist[cols], fut[cols][fut["date"] > hist["date"].max()]], ignore_index=True)
    return overlay_calendar(cal.sort_values("date").reset_index(drop=True))


def _live_holidays() -> dict[str, str]:
    """India public holidays and observances from Google's public calendar, cached for a day.

    Returns {iso_date: event name}. Empty dict if the feed cannot be reached (offline, blocked); the
    month still renders from the project's own data, just without the "confirmed online" badge.
    """
    global _live_cache
    if _live_cache and time.time() - _live_cache[0] < _LIVE_TTL_S:
        return _live_cache[1]
    try:
        with httpx.Client(timeout=6.0, follow_redirects=True) as client:
            r = client.get(LIVE_CALENDAR_URL)
        r.raise_for_status()
        out = {}
        for ymd, name in LIVE_EVENT.findall(r.text):
            out[f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"] = name.strip()
    except httpx.HTTPError:
        out = _live_cache[1] if _live_cache else {}  # keep the last good copy rather than blanking it on a blip
    _live_cache = (time.time(), out)
    return out


@router.get("/calendar")
def calendar(month: str) -> dict:
    """One calendar month: `month` is YYYY-MM. Each day: flags from the project data plus, when available,
    the matching live public holiday name."""
    start = pd.Timestamp(f"{month}-01")
    end = start + pd.offsets.MonthEnd(1)
    cal = _combined_calendar()
    rows = cal[(cal["date"] >= start) & (cal["date"] <= end)].sort_values("date")
    live = _live_holidays()
    today = Date.fromisoformat(C.TODAY)
    days = []
    for _, r in rows.iterrows():
        iso = str(r["date"].date())
        live_name = live.get(iso)
        note = r["event_note"] if isinstance(r["event_note"], str) else ""
        days.append({
            "date": iso, "weekday": r["day_of_week"], "is_weekend": bool(r["is_weekend"]),
            "is_today": Date.fromisoformat(iso) == today,
            "holiday": bool(r["tn_public_holiday"]) or bool(r["special_declared_holiday"]),
            "holiday_name": (r["holiday_name"] or None) if isinstance(r["holiday_name"], str) else None,
            "festival": bool(r["major_festival"]), "rain_holiday": bool(r["rain_holiday_colleges"]),
            "exam_week": bool(r["university_exam_any"]), "formative_test": bool(r["formative_test_any"]),
            "students_mostly_away": bool(r["students_mostly_away"]),
            "event_note": note if note and not note.startswith(BOILERPLATE_NOTE_PREFIX) else None,
            "live_holiday_name": live_name, "live_confirmed": live_name is not None,
        })
    return {"month": month, "days": days, "live_checked": bool(live),
            "live_source": "Google's public \"Holidays in India\" calendar" if live else "offline (showing the project's own calendar only)"}
