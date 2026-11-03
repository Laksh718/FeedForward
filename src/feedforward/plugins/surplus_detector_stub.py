"""Plug in point for the surplus and anomaly detector.

The real implementation is `feedforward.models.surplus_detector.InventoryAwareSurplusDetector` (used by
ForecastService by default). StubSurplusDetector below is kept only as a minimal reference for the interface.
"""

from typing import Protocol

RISK_LEVELS = ("low", "medium", "high")


class SurplusDetector(Protocol):
    """Interface: given the usual plan, the forecast range and (optionally) inventory facts for one dish and
    date, return low, medium or high."""

    def assess(self, usual_plan: float, p50: float, p90: float, *, min_days_to_expiry: float | None = None,
               stock_cover_days: float | None = None, kg_expiring_within_3_days: float | None = None) -> str:
        """Surplus and anomaly risk level for one dish."""
        ...


class StubSurplusDetector:
    """Minimal reference implementation. Thresholds on the usual plan versus the forecast range only;
    ignores inventory facts. See InventoryAwareSurplusDetector for the one actually used."""

    medium_ratio = 1.10  # usual plan more than 10 percent above the most likely demand

    def assess(self, usual_plan: float, p50: float, p90: float, **_ignored) -> str:
        """High if the usual plan is above even the high end, medium if well above most likely, else low."""
        if usual_plan <= 0:
            return "low"
        if usual_plan > p90:
            return "high"
        return "medium" if usual_plan > p50 * self.medium_ratio else "low"
