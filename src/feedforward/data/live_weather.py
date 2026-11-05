"""Real weather for Kattankulathur from Open-Meteo (free, no key): recorded days and a 16 day forecast.

The dataset's weather file ends with the history (2026-10-05). For later dates this module supplies:
- observed: Open-Meteo's archive (reanalysis) and recent days of its forecast model, for dates up to the real today;
- forecast: Open-Meteo's forecast for the next 16 days.
Dates beyond that keep last year's monthly average (flagged as assumed) in features.full_weather.

Data is refreshed at most once an hour, kept in memory and on disk (artifacts/live/), so a restart without internet
still has the last good copy. Set FEEDFORWARD_LIVE_WEATHER=0 to switch it off (the tests do, to stay offline).
"""

import hashlib
import os
import threading
import time
from datetime import date, datetime, timedelta, timezone

import httpx
import pandas as pd

from feedforward import config as C

LATITUDE, LONGITUDE = 12.8231, 80.0442   # SRM Kattankulathur, the hostel the weather file describes
TIMEZONE = "Asia/Kolkata"
IST = timezone(timedelta(hours=5, minutes=30))
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
DAILY = "temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code"
TTL_S = 3600
FORECAST_DAYS = 16
CACHE_CSV = C.ARTIFACTS_DIR / "live" / "open_meteo_weather.csv"
COLUMNS = ["date", "temp_max_c", "temp_min_c", "precipitation_mm", "weather_code", "condition", "source"]

# WMO weather code -> (condition text, rain level 0 none, 1 light, 2 moderate or thunder, 3 heavy), the dataset's scale.
WMO = {
    0: ("Clear", 0), 1: ("Mainly clear", 0), 2: ("Partly cloudy", 0), 3: ("Overcast", 0),
    45: ("Fog", 0), 48: ("Fog", 0),
    51: ("Light drizzle", 1), 53: ("Drizzle", 1), 55: ("Heavy drizzle", 1), 56: ("Drizzle", 1), 57: ("Drizzle", 1),
    61: ("Light rain", 1), 63: ("Rain", 2), 65: ("Heavy rain", 3), 66: ("Rain", 2), 67: ("Heavy rain", 3),
    80: ("Light showers", 1), 81: ("Rain showers", 2), 82: ("Heavy showers", 3),
    95: ("Thunderstorm", 2), 96: ("Thunderstorm", 2), 99: ("Heavy thunderstorm", 3),
}

_lock = threading.Lock()
_state: dict = {"fetched_at": 0.0, "frame": None, "version": "none"}


def enabled() -> bool:
    return os.getenv("FEEDFORWARD_LIVE_WEATHER", "1").strip().lower() not in ("0", "false", "no", "off")


def real_today() -> date:
    """Today's date in India (the live data's clock, not the project's simulated today)."""
    return datetime.now(IST).date()


def rain_level(code, precipitation_mm) -> int:
    """Rain level from the WMO code and the day's rainfall (IMD bands: 15.6 mm moderate, 64.5 mm heavy)."""
    mm = 0.0 if pd.isna(precipitation_mm) else float(precipitation_mm)
    from_code = WMO.get(int(code), ("", 0))[1] if pd.notna(code) and mm >= 0.5 else 0
    from_mm = 3 if mm >= 64.5 else 2 if mm >= 15.6 else 1 if mm >= 2.5 else 0
    return max(from_code, from_mm)


RAIN_WORDS = ("Dry", "Light rain", "Rain", "Heavy rain")


def condition_for(code, level: int) -> str:
    """The WMO wording, unless the day's rainfall says otherwise (a trace of drizzle is dry, a downpour is heavy)."""
    text, code_level = WMO.get(int(code), ("", 0)) if pd.notna(code) else ("", 0)
    if not text or (code_level > 0 and level == 0):
        return "Dry, cloudy" if text else RAIN_WORDS[level]
    if level > code_level:
        return "Thunderstorm, heavy rain" if text.endswith("Thunderstorm") and level == 3 else RAIN_WORDS[level]
    return text


def _daily_frame(payload: dict) -> pd.DataFrame:
    d = payload.get("daily") or {}
    df = pd.DataFrame({"date": pd.to_datetime(d.get("time", [])),
                       "temp_max_c": d.get("temperature_2m_max", []), "temp_min_c": d.get("temperature_2m_min", []),
                       "precipitation_mm": d.get("precipitation_sum", []), "weather_code": d.get("weather_code", [])})
    return df.dropna(subset=["temp_max_c", "temp_min_c"])


def fetch(today: date | None = None) -> pd.DataFrame:
    """Download recorded weather from the day after the history up to today, and the forecast after it."""
    today = today or real_today()
    first = pd.Timestamp(C.HISTORY_END).date() + timedelta(days=1)
    base = {"latitude": LATITUDE, "longitude": LONGITUDE, "daily": DAILY, "timezone": TIMEZONE}
    frames = []
    with httpx.Client(timeout=6.0) as client:
        r = client.get(FORECAST_URL, params={**base, "past_days": 7, "forecast_days": FORECAST_DAYS})
        r.raise_for_status()
        frames.append(_daily_frame(r.json()))
        archive_end = today - timedelta(days=2)   # the archive lags a few days; the forecast model covers the rest
        if archive_end >= first:
            r = client.get(ARCHIVE_URL, params={**base, "start_date": first.isoformat(), "end_date": archive_end.isoformat()})
            r.raise_for_status()
            frames.insert(0, _daily_frame(r.json()))   # first, so its recorded values win over the forecast model
    df = pd.concat(frames, ignore_index=True).drop_duplicates("date", keep="first")
    df = df[df["date"].dt.date >= first].sort_values("date").reset_index(drop=True)
    df["condition"] = [WMO.get(int(c), ("Unknown", 0))[0] if pd.notna(c) else "Unknown" for c in df["weather_code"]]
    df["source"] = ["observed" if d <= today else "forecast" for d in df["date"].dt.date]
    return df[COLUMNS]


def _load_disk() -> pd.DataFrame | None:
    try:
        return pd.read_csv(CACHE_CSV, parse_dates=["date"], encoding="utf-8")[COLUMNS]
    except (OSError, ValueError, KeyError):
        return None


def _fingerprint(df: pd.DataFrame | None) -> str:
    if df is None or df.empty:
        return "none"
    return hashlib.sha1(df.to_csv(index=False).encode()).hexdigest()[:12]


def live_weather() -> pd.DataFrame | None:
    """The latest Open-Meteo rows (refreshed at most hourly), or None when switched off or never reachable."""
    if not enabled():
        return None
    with _lock:
        # A recent answer stands, including a failed one: without this, a server that cannot reach Open-Meteo and has no
        # saved copy would try the network again for every forecast it makes (a 7 day plans board makes 28 of them).
        if _state["fetched_at"] and time.time() - _state["fetched_at"] < TTL_S:
            return _state["frame"]
        try:
            df, ok = fetch(), True
        except (httpx.HTTPError, ValueError, KeyError):
            df, ok = (_state["frame"] if _state["frame"] is not None else _load_disk()), False  # keep the last good copy
        if ok:
            try:
                CACHE_CSV.parent.mkdir(parents=True, exist_ok=True)
                df.to_csv(CACHE_CSV, index=False, encoding="utf-8")
            except OSError:
                pass  # a read only disk only loses the offline copy
        # A failed fetch retries after 10 minutes, not a full hour.
        _state["fetched_at"] = time.time() if ok else time.time() - TTL_S + 600
        _state["frame"], _state["version"] = df, _fingerprint(df)
        return df


def version() -> str:
    """Changes whenever the live weather data changes (used to expire cached forecasts)."""
    live_weather()
    return _state["version"]


def weather_rows(dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Live rows for the requested dates, in the shape of features.full_weather (may be empty)."""
    cols = ["date", "temp_max_c", "temp_min_c", "temp_mean_c", "rain_level", "weather_reliable", "weather_assumed",
            "weather_source", "weather_condition"]
    df = live_weather()
    if df is None or df.empty:
        return pd.DataFrame(columns=cols)
    df = df[df["date"].isin(dates)]
    out = pd.DataFrame({"date": df["date"], "temp_max_c": df["temp_max_c"].astype(float),
                        "temp_min_c": df["temp_min_c"].astype(float)})
    out["temp_mean_c"] = (out["temp_max_c"] + out["temp_min_c"]) / 2
    out["rain_level"] = [rain_level(c, mm) for c, mm in zip(df["weather_code"], df["precipitation_mm"], strict=True)]
    out["weather_reliable"], out["weather_assumed"] = 1, 0
    out["weather_source"] = df["source"].to_numpy()
    out["weather_condition"] = [condition_for(c, lvl) for c, lvl in zip(df["weather_code"], out["rain_level"], strict=True)]
    return out[cols].reset_index(drop=True)
