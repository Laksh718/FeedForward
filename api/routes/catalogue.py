"""GET /api/dishes and GET /api/ingredients"""

from datetime import date as Date

import pandas as pd
from fastapi import APIRouter

from api.schemas import Slot
from feedforward import config as C
from feedforward.data.features import menu_rows_for

router = APIRouter()


def _read(name: str) -> pd.DataFrame:
    return pd.read_parquet(C.PROCESSED_DIR / f"{name}.parquet")


@router.get("/dishes")
def dishes(date: Date | None = None, slot: Slot | None = None) -> dict:
    """The dish catalogue. With date and slot, only the dishes on the menu then (in menu order)."""
    cat = _read("dishes")[["dish_id", "dish_name", "category", "diet", "forecast_priority", "portion_g", "popularity_score"]]
    if date and slot:
        menu = menu_rows_for(pd.DatetimeIndex([pd.Timestamp(date)]), _read("weekly_menu"))
        ids = menu.loc[menu["meal_slot"] == slot, "dish_id"].tolist()
        cat = cat.set_index("dish_id").loc[ids].reset_index()
    return {"count": len(cat), "dishes": cat.to_dict(orient="records")}


@router.get("/ingredients")
def ingredients() -> dict:
    """The ingredient master (70 ingredients)."""
    ing = _read("inventory_ingredients")
    return {"count": len(ing), "ingredients": ing.to_dict(orient="records")}
