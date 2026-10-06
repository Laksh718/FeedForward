"""Expected columns of every dataset file, used to validate files on load."""

from dataclasses import dataclass
from pathlib import Path

from feedforward import config as C


@dataclass(frozen=True)
class TableSpec:
    """Where a table lives, which columns it must have and which are dates."""

    path: Path
    columns: tuple[str, ...]
    date_cols: tuple[str, ...] = ()


KITCHEN_COLS = (
    "date", "day_of_week", "meal_slot", "dish_id", "dish_name", "category",
    "forecast_priority", "diet", "is_choice", "n_options", "special_limited",
    "enrolled", "students_present", "attendance", "prepared_qty", "topup_qty",
    "consumed_qty", "unmet_qty", "leftover_qty", "leftover_kg",
)

TABLES: dict[str, TableSpec] = {
    "kitchen_history": TableSpec(C.KITCHEN_DIR / "kitchen_history.csv", KITCHEN_COLS, ("date",)),
    "kitchen_history_raw": TableSpec(
        C.KITCHEN_DIR / "kitchen_history_raw.csv", KITCHEN_COLS, ("date",)
    ),
    "calendar": TableSpec(
        C.CALENDAR_DIR / "calendar_real.csv",
        (
            "date", "day_of_week", "is_weekend", "week_of_year", "month", "tn_public_holiday",
            "holiday_name", "major_festival", "special_declared_holiday",
            "compensatory_working_day", "rain_holiday_colleges", "rain_holiday_schools_only",
            "senior_phase", "first_year_phase", "phase_confidence", "university_exam_any",
            "formative_test_any", "students_mostly_away", "event_note", "source_codes",
        ),
        ("date",),
    ),
    "calendar_sources": TableSpec(
        C.CALENDAR_DIR / "calendar_sources.csv", ("code", "source", "url", "used_for")
    ),
    "weather": TableSpec(
        C.CALENDAR_DIR / "weather_kattankulathur.csv",
        (
            "date", "condition", "temp_max_c", "temp_min_c", "temp_mean_c",
            "rainfall_mm_reported", "rain_level", "rain_level_basis", "data_quality", "source",
        ),
        ("date",),
    ),
    "dishes": TableSpec(
        C.MENU_DIR / "dishes.csv",
        ("dish_id", "dish_name", "category", "diet", "forecast_priority", "portion_g",
         "popularity_score"),
    ),
    "recipes": TableSpec(
        C.MENU_DIR / "recipes.csv", ("dish_id", "dish_name", "ingredient", "qty_g_per_portion")
    ),
    "weekly_menu": TableSpec(
        C.MENU_DIR / "weekly_menu.csv",
        ("menu_version", "valid_from", "valid_to", "day_of_week", "meal_slot", "item_order",
         "is_choice", "n_options", "dish_id", "dish_name", "condition"),
        ("valid_from", "valid_to"),
    ),
    "inventory_batches": TableSpec(
        C.INVENTORY_DIR / "inventory_batches.csv",
        ("batch_id", "ingredient", "storage_type", "received_date", "received_qty_kg",
         "shelf_life_days", "expiry_date", "used_kg", "expired_kg", "remaining_end_of_year_kg"),
        ("received_date", "expiry_date"),
    ),
    "inventory_daily": TableSpec(
        C.INVENTORY_DIR / "inventory_daily.csv",
        ("date", "ingredient", "cycle_day", "opening_stock_kg", "delivered_kg", "used_kg",
         "expired_kg", "emergency_purchase_kg", "closing_stock_kg", "days_to_nearest_expiry",
         "kg_expiring_within_3_days"),
        ("date",),
    ),
    "inventory_ingredients": TableSpec(
        C.INVENTORY_DIR / "inventory_ingredients.csv",
        ("ingredient", "storage_type", "nominal_shelf_life_days", "pack_kg", "prep_loss_factor",
         "cover_days_per_delivery", "avg_daily_use_kg"),
    ),
}
