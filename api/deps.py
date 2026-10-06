"""Shared dependencies: the forecast service is loaded once and reused."""

import os
from functools import lru_cache

from dotenv import load_dotenv
from fastapi import HTTPException

from feedforward import config as C
from feedforward.models.forecast_service import ForecastService

load_dotenv(C.PROJECT_ROOT / ".env")


def error(status: int, message: str, fix: str) -> HTTPException:
    """Error that says what happened and how to fix it."""
    return HTTPException(status_code=status, detail={"message": message, "fix": fix})


@lru_cache(maxsize=1)
def _load() -> ForecastService:
    return ForecastService()


def get_service() -> ForecastService:
    """FastAPI dependency. Returns a clear 503 when the model has not been trained yet."""
    try:
        return _load()
    except FileNotFoundError as exc:
        raise error(503, "The forecast model is not available.",
                    "Run: python -m feedforward.data.timeseries, then python -m feedforward.models.train, "
                    "then python -m feedforward.models.train --final") from exc


def reload_service() -> None:
    """Forget the loaded model (used after retraining or when new history is saved)."""
    _load.cache_clear()


def cors_origins() -> list[str]:
    """CORS is closed unless CORS_ORIGINS (comma separated) is set in .env."""
    raw = os.getenv("CORS_ORIGINS", "")
    return [o.strip() for o in raw.split(",") if o.strip()]
