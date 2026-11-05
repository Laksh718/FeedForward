"""Shared test setup: keep the suite offline and deterministic (no live Open-Meteo weather)."""

import os

os.environ.setdefault("FEEDFORWARD_LIVE_WEATHER", "0")
