"""Plug in point for the surplus and anomaly detector (teammate). The default below is a clearly marked STUB."""

from typing import Protocol

RISK_LEVELS = ("low", "medium", "high")


class SurplusDetector(Protocol):
    """Interface: given the usual plan and the forecast range of one dish, return low, medium or high."""

    def assess(self, usual_plan: float, p50: float, p90: float) -> str:
        """Surplus risk level for one dish."""
        ...


class StubSurplusDetector:
    """STUB, not the real detector. Simple thresholds on the usual plan versus the forecast range."""

    medium_ratio = 1.10  # usual plan more than 10 percent above the most likely demand

    def assess(self, usual_plan: float, p50: float, p90: float) -> str:
        """High if the usual plan is above even the high end, medium if well above most likely, else low."""
        if usual_plan <= 0:
            return "low"
        if usual_plan > p90:
            return "high"
        return "medium" if usual_plan > p50 * self.medium_ratio else "low"
