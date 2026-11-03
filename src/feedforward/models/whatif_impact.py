"""What a what if changes beyond the total: dish by dish, attendance, surplus risk, and the ingredients it needs.

Ingredient kilograms are the recipe grams per portion times the portions to cook, raised by each ingredient's
preparation loss factor (what has to be bought or taken from the store, not what ends up on the plate). The data has
no ingredient prices, so the extra spend is shown as kilograms and supplier packs, never as invented money.
"""

import math
from functools import lru_cache

import pandas as pd

from feedforward import config as C

NOTES = [
    "Ingredient kilograms are recipe grams per portion times the portions to cook, including preparation loss.",
    "The data has no ingredient prices, so the extra spend is shown as kilograms and supplier packs.",
]


@lru_cache(maxsize=1)
def _recipes() -> pd.DataFrame:
    return pd.read_parquet(C.PROCESSED_DIR / "recipes.parquet")[["dish_id", "ingredient", "qty_g_per_portion"]]


@lru_cache(maxsize=1)
def _ingredients() -> pd.DataFrame:
    return pd.read_parquet(C.PROCESSED_DIR / "inventory_ingredients.parquet").set_index("ingredient")


def ingredient_kg(dishes: list[dict], key: str = "recommended") -> dict[str, float]:
    """Kilograms of each ingredient needed to cook `key` portions of every dish, including preparation loss."""
    portions = {d["dish_id"]: d[key] for d in dishes if d.get(key)}
    rec = _recipes()
    rec = rec[rec["dish_id"].isin(portions)]
    if rec.empty:
        return {}
    kg = (rec["dish_id"].map(portions) * rec["qty_g_per_portion"] / 1000).groupby(rec["ingredient"]).sum()
    loss = _ingredients()["prep_loss_factor"].reindex(kg.index).fillna(1.0)
    return (kg * loss).to_dict()


def _packs(kg: float, pack_kg: float | None) -> int | None:
    return math.ceil(kg / pack_kg - 1e-9) if pack_kg and kg > 0 else (0 if pack_kg else None)


def _num(value) -> float | None:
    return None if value is None or pd.isna(value) else float(value)


def impact(base: dict, changed: dict) -> dict:
    """Compare the plan without and with the what if (both plan responses for the same date, slot and scope)."""
    b = {d["dish_id"]: d for d in base["dishes"]}
    c = {d["dish_id"]: d for d in changed["dishes"]}
    dishes = []
    for dish_id in list(c) + [i for i in b if i not in c]:
        old, new = b.get(dish_id, {}), c.get(dish_id, {})
        before, after = int(old.get("recommended", 0)), int(new.get("recommended", 0))
        dishes.append({
            "dish_id": dish_id, "dish_name": new.get("dish_name") or old.get("dish_name"),
            "before": before, "after": after, "change": after - before,
            "change_pct": round(100 * (after - before) / before, 1) if before else None,
            "most_likely_before": int(old.get("p50", 0)), "most_likely_after": int(new.get("p50", 0)),
            "risk_before": old.get("surplus_risk"), "risk_after": new.get("surplus_risk"),
        })
    dishes.sort(key=lambda d: (-abs(d["change"]), d["dish_name"] or ""))

    kb, kc, info = ingredient_kg(base["dishes"]), ingredient_kg(changed["dishes"]), _ingredients()
    rows = []
    for name in sorted(set(kb) | set(kc)):
        before, after = round(kb.get(name, 0.0), 1), round(kc.get(name, 0.0), 1)
        if before == 0 and after == 0:
            continue
        pack = _num(info["pack_kg"].get(name)) if name in info.index else None
        daily = _num(info["avg_daily_use_kg"].get(name)) if name in info.index else None
        packs_before, packs_after = _packs(before, pack), _packs(after, pack)
        rows.append({
            "ingredient": name, "storage_type": info["storage_type"].get(name) if name in info.index else None,
            "before_kg": before, "after_kg": after, "change_kg": round(after - before, 1),
            "pack_kg": pack, "packs_before": packs_before, "packs_after": packs_after,
            "packs_change": None if packs_before is None else packs_after - packs_before,
            "change_pct_of_daily_use": round(100 * (after - before) / daily, 1) if daily else None,
        })
    rows.sort(key=lambda r: (-abs(r["change_kg"]), r["ingredient"]))
    total_before, total_after = round(sum(kb.values()), 1), round(sum(kc.values()), 1)
    packs = [r["packs_change"] for r in rows if r["packs_change"] is not None]
    return {
        "attendance": {"before": base["expected_attendance"], "after": changed["expected_attendance"]},
        "risk": {"before": base["risk_counts"], "after": changed["risk_counts"]},
        "dishes": dishes,
        "ingredients": rows,
        "ingredient_totals": {"before_kg": total_before, "after_kg": total_after, "change_kg": round(total_after - total_before, 1),
                              "packs_change": sum(packs), "ingredients_more": sum(r["change_kg"] > 0 for r in rows),
                              "ingredients_less": sum(r["change_kg"] < 0 for r in rows)},
        "scope": changed.get("scope"),
        "notes": NOTES,
    }
