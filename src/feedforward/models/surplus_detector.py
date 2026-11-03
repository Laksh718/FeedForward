"""Real surplus and anomaly detector, combining the forecast range with inventory facts.

Two independent signals, the worse of the two wins:
- demand risk: the usual (fixed) plan compared with the forecast range -- the same overshoot logic as
  the reference stub (plugins/surplus_detector_stub.py).
- inventory risk: ingredients of the dish close to expiry, or already short of stock cover. A dish can
  look fine on demand alone and still be a surplus-and-waste risk because what is on the shelf is about
  to spoil, or a shortage risk because there is almost no stock cover left.
`ForecastService` uses this by default and feeds it the per date and dish rows of
`artifacts/timeseries/inventory_features.parquet` (min_days_to_expiry, stock_cover_days,
kg_expiring_within_3_days); any value not available is passed as None and simply skipped.
"""

from feedforward.plugins.surplus_detector_stub import RISK_LEVELS

_RANK = {level: i for i, level in enumerate(RISK_LEVELS)}


class InventoryAwareSurplusDetector:
    """See module docstring. All thresholds are class attributes so a teammate can tune them."""

    medium_ratio = 1.10     # usual plan more than 10 percent above the most likely demand -> medium
    expiry_high_days = 1    # soonest ingredient expiry is tomorrow or sooner -> high
    expiry_medium_days = 3  # soonest ingredient expiry within 3 days, with stock already flagged -> medium
    low_cover_days = 1      # less than a day of stock cover left -> high (shortage, not surplus)

    def assess(self, usual_plan: float, p50: float, p90: float, *, min_days_to_expiry: float | None = None,
               stock_cover_days: float | None = None, kg_expiring_within_3_days: float | None = None) -> str:
        """Surplus and anomaly risk level for one dish: the higher of the demand risk and the inventory risk."""
        demand = self._demand_risk(usual_plan, p50, p90)
        inventory = self._inventory_risk(min_days_to_expiry, stock_cover_days, kg_expiring_within_3_days)
        return max(demand, inventory, key=_RANK.__getitem__)

    def _demand_risk(self, usual_plan: float, p50: float, p90: float) -> str:
        """High if the usual plan is above even the high end, medium if well above most likely, else low."""
        if usual_plan <= 0:
            return "low"
        if usual_plan > p90:
            return "high"
        return "medium" if usual_plan > p50 * self.medium_ratio else "low"

    def _inventory_risk(self, min_days_to_expiry: float | None, stock_cover_days: float | None,
                         kg_expiring_within_3_days: float | None) -> str:
        """High for near-expiry ingredients or a near-empty stock cover; medium for soon-expiring stock."""
        if stock_cover_days is not None and stock_cover_days <= self.low_cover_days:
            return "high"
        if min_days_to_expiry is not None and min_days_to_expiry <= self.expiry_high_days:
            return "high"
        if min_days_to_expiry is not None and min_days_to_expiry <= self.expiry_medium_days and \
                kg_expiring_within_3_days:
            return "medium"
        return "low"
