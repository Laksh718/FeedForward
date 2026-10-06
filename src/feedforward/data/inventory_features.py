"""Inventory features per date and dish, for teammates and the dashboard (not the demand model)."""

import pandas as pd

from feedforward import config as C

EXPIRY_CAP_DAYS = 30  # days_to_nearest_expiry is empty when there is no stock; treat as "plenty of time"


def inventory_features(recipes: pd.DataFrame, daily: pd.DataFrame, ingredients: pd.DataFrame) -> pd.DataFrame:
    """Per date and dish: soonest expiry of its ingredients, stock cover in days, kg expiring soon."""
    use = ingredients.set_index("ingredient")["avg_daily_use_kg"].clip(lower=1e-6)
    d = daily.copy()
    d["days_to_nearest_expiry"] = d["days_to_nearest_expiry"].fillna(EXPIRY_CAP_DAYS).clip(upper=EXPIRY_CAP_DAYS)
    d["cover_days"] = d["closing_stock_kg"] / d["ingredient"].map(use)
    joined = recipes[["dish_id", "ingredient"]].merge(
        d[["date", "ingredient", "days_to_nearest_expiry", "cover_days", "kg_expiring_within_3_days"]], on="ingredient")
    out = joined.groupby(["date", "dish_id"], as_index=False).agg(
        min_days_to_expiry=("days_to_nearest_expiry", "min"), stock_cover_days=("cover_days", "min"),
        kg_expiring_within_3_days=("kg_expiring_within_3_days", "sum"))
    return out


def main() -> None:
    """Write artifacts/timeseries/inventory_features.parquet."""
    p = C.PROCESSED_DIR
    out = inventory_features(pd.read_parquet(p / "recipes.parquet"), pd.read_parquet(p / "inventory_daily.parquet"),
                             pd.read_parquet(p / "inventory_ingredients.parquet"))
    out.to_parquet(C.TIMESERIES_DIR / "inventory_features.parquet", index=False)
    print(f"inventory_features: {out.shape}")
    print(out.describe().round(1).to_string())


if __name__ == "__main__":
    main()
