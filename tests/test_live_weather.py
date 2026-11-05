"""Live weather (Open-Meteo): rain levels, the merge into full_weather, and the offline fallback. No network."""

from datetime import date

import pandas as pd
import pytest

from feedforward.data import features
from feedforward.data import live_weather as lw


def _fake_frame():
    return pd.DataFrame({"date": pd.to_datetime(["2026-10-06", "2026-10-07", "2026-11-10"]),
                         "temp_max_c": [33.4, 31.0, 29.6], "temp_min_c": [25.2, 24.1, 23.8],
                         "precipitation_mm": [0.0, 20.5, 3.0], "weather_code": [2, 95, 80],
                         "condition": ["Partly cloudy", "Thunderstorm", "Light showers"],
                         "source": ["observed", "observed", "forecast"]})[lw.COLUMNS]


@pytest.fixture
def live(monkeypatch, tmp_path):
    monkeypatch.setenv("FEEDFORWARD_LIVE_WEATHER", "1")
    monkeypatch.setattr(lw, "CACHE_CSV", tmp_path / "w.csv")
    monkeypatch.setattr(lw, "fetch", lambda today=None: _fake_frame())
    monkeypatch.setattr(lw, "_state", {"fetched_at": 0.0, "frame": None, "version": "none"})


def test_rain_level_from_code_and_rainfall():
    assert lw.rain_level(2, 0.0) == 0
    assert lw.rain_level(61, 0.2) == 0        # a trace is dry
    assert lw.rain_level(80, 3.0) == 1
    assert lw.rain_level(95, 4.0) == 2        # thunder
    assert lw.rain_level(3, 20.0) == 2        # IMD moderate by rainfall
    assert lw.rain_level(65, 80.0) == 3


def test_live_rows_fill_dates_after_history(live):
    dates = pd.DatetimeIndex(pd.to_datetime(["2026-10-05", "2026-10-06", "2026-10-07", "2026-12-25"]))
    w = features.full_weather(dates).set_index("date")
    assert w.loc["2026-10-05", "weather_source"] == "recorded"     # the dataset still wins
    assert w.loc["2026-10-06", "weather_source"] == "observed"
    assert w.loc["2026-10-06", "weather_assumed"] == 0 and w.loc["2026-10-06", "temp_max_c"] == pytest.approx(33.4)
    assert w.loc["2026-10-07", "rain_level"] == 2 and w.loc["2026-10-07", "weather_condition"] == "Thunderstorm"
    assert w.loc["2026-12-25", "weather_source"] == "assumed" and w.loc["2026-12-25", "weather_assumed"] == 1
    assert (tmp := lw.CACHE_CSV).exists() and len(pd.read_csv(tmp)) == 3


def test_offline_keeps_last_copy_and_switch_off(live, monkeypatch):
    first = lw.live_weather()
    v = lw.version()

    def boom(today=None):
        raise lw.httpx.ConnectError("offline")
    monkeypatch.setattr(lw, "fetch", boom)
    lw._state["fetched_at"] = 0.0
    assert lw.live_weather() is first and lw.version() == v
    monkeypatch.setenv("FEEDFORWARD_LIVE_WEATHER", "0")
    assert lw.live_weather() is None


def test_daily_frame_parses_payload_and_drops_empty_days():
    payload = {"daily": {"time": ["2026-11-04", "2026-11-05", "2026-11-06"], "temperature_2m_max": [31, None, 29],
                         "temperature_2m_min": [24, None, 23], "precipitation_sum": [0, None, 8.7], "weather_code": [2, None, 95]}}
    df = lw._daily_frame(payload)
    assert list(df["date"].dt.date) == [date(2026, 11, 4), date(2026, 11, 6)]


def test_condition_follows_rain_level():
    assert lw.condition_for(51, 0) == "Dry, cloudy"
    assert lw.condition_for(80, 2) == "Rain"
    assert lw.condition_for(95, 2) == "Thunderstorm"
    assert lw.condition_for(2, 0) == "Partly cloudy"


def test_unreachable_with_no_saved_copy_is_tried_once_not_for_every_forecast(monkeypatch, tmp_path):
    """As on a fresh cloud server that cannot reach Open-Meteo: one attempt, then the answer stands for 10 minutes."""
    import httpx

    calls = []

    def down(today=None):
        calls.append(1)
        raise httpx.ConnectError("unreachable")
    monkeypatch.setenv("FEEDFORWARD_LIVE_WEATHER", "1")
    monkeypatch.setattr(lw, "CACHE_CSV", tmp_path / "none.csv")
    monkeypatch.setattr(lw, "fetch", down)
    monkeypatch.setattr(lw, "_state", {"fetched_at": 0.0, "frame": None, "version": "none"})
    for _ in range(28):                     # a 7 day plans board asks for the weather version 28 times
        assert lw.version() == "none"
        assert lw.weather_rows(pd.DatetimeIndex(["2026-11-10"])).empty
    assert len(calls) == 1
    monkeypatch.setattr(lw.time, "time", lambda: lw._state["fetched_at"] + lw.TTL_S + 1)   # after the 10 minute retry window
    lw.version()
    assert len(calls) == 2
