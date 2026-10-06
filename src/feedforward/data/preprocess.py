"""M1 preprocessing: validate, unify types and ids, normalise text, write artifacts/processed/."""

import re

import pandas as pd

from feedforward import config as C
from feedforward.data.loaders import load_all
from feedforward.data.nlp_text import (
    clean_text,
    display_name,
    fuzzy_match,
    lemmatize,
    match_key,
    setup_nltk,
)
from feedforward.data.text_features import DishTextModel

# Weather words -> flags. Condition text is semi structured: one short phrase per day.
WEATHER_FLAGS = {"is_thunder": r"thunder", "is_drizzle": r"drizzle|shower", "is_fog": r"fog|mist|haze|smoke",
                 "is_rain_text": r"rain|drizzle|shower|thunder"}
# Event kinds found in the free text calendar notes.
EVENT_KINDS = {"rain_holiday": r"rain holiday", "compensatory": r"compensatory", "cyclone": r"cyclone",
               "monsoon": r"monsoon", "bank_only": r"bank"}


def normalise_ids(df: pd.DataFrame) -> pd.DataFrame:
    """Unify ids: dish_id upper case and trimmed, ingredient lower case and trimmed."""
    df = df.copy()
    if "dish_id" in df:
        df["dish_id"] = df["dish_id"].astype(str).str.strip().str.upper()
    if "ingredient" in df:
        df["ingredient"] = df["ingredient"].astype(str).map(clean_text).str.lower()
    return df


def dish_catalogue(dishes: pd.DataFrame) -> dict[str, str]:
    """match_key -> dish_id; fails loudly if two dishes share one key after normalising."""
    keys = dishes["dish_name"].map(match_key)
    clash = dishes.loc[keys.duplicated(keep=False), "dish_name"].tolist()
    if clash:
        raise ValueError(f"Dish names collide after normalising: {clash}")
    return dict(zip(keys, dishes["dish_id"], strict=True))


def process_dishes(dishes: pd.DataFrame, model: DishTextModel) -> pd.DataFrame:
    """Add display name, match key, lemma tokens and the text embedding to the catalogue."""
    out = dishes.copy()
    out["dish_name"] = out["dish_name"].map(display_name)
    out["match_key"] = out["dish_name"].map(match_key)
    out["lemmas"] = out["match_key"].map(lambda s: " ".join(lemmatize(w) for w in s.split()))
    return out.merge(model.embedding_table(), on="dish_id", how="left")


def process_weather(weather: pd.DataFrame) -> pd.DataFrame:
    """Normalise condition text, add text flags and reliability flags."""
    w = weather.copy()
    w["condition"] = w["condition"].map(display_name)
    key = w["condition"].map(match_key)
    for col, pattern in WEATHER_FLAGS.items():
        w[col] = key.str.contains(pattern).astype(int)
    w["weather_reliable"] = (~w["data_quality"].str.upper().str.startswith("UNVERIFIED")).astype(int)
    w["temp_outlier"] = w["data_quality"].str.lower().str.contains("outlier").astype(int)
    return w.drop(columns=["rainfall_mm_reported"])  # always 0, not usable


def process_calendar(cal: pd.DataFrame) -> pd.DataFrame:
    """Normalise holiday and event names, add event kind flags from the free text note."""
    c = cal.copy()
    c["holiday_name"] = c["holiday_name"].fillna("").map(display_name)
    note = c["event_note"].fillna("").map(clean_text)
    c["event_note"] = note
    low = note.str.lower()
    for col, pattern in EVENT_KINDS.items():
        c[f"event_{col}"] = low.str.contains(pattern, flags=re.I).astype(int)
    c["phase_estimated"] = (c["phase_confidence"] == "estimated").astype(int)
    return c


def map_kitchen_names(raw: pd.DataFrame, catalogue: dict[str, str]) -> pd.DataFrame:
    """Map every distinct raw dish name to a dish_id. Returns name, id, score, review flag."""
    rows = []
    for name in raw["dish_name"].dropna().unique():
        res = fuzzy_match(name, catalogue)
        rows.append({"raw_name": name, "dish_id": res.match, "score": round(res.score, 1),
                     "needs_review": res.needs_review})
    return pd.DataFrame(rows)


def main() -> None:
    """Run the whole M1 pipeline and write processed tables."""
    setup_nltk()
    C.PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    t = load_all()
    dishes = normalise_ids(t["dishes"])
    catalogue = dish_catalogue(dishes)
    model = DishTextModel().fit(dishes)
    outputs = {
        "dishes": process_dishes(dishes, model),
        "weather": process_weather(t["weather"]),
        "calendar": process_calendar(t["calendar"]),
        "weekly_menu": normalise_ids(t["weekly_menu"]),
        "recipes": normalise_ids(t["recipes"]),
        "inventory_ingredients": normalise_ids(t["inventory_ingredients"]),
        "inventory_batches": normalise_ids(t["inventory_batches"]),
        "inventory_daily": normalise_ids(t["inventory_daily"]),
        "dish_name_map": map_kitchen_names(t["kitchen_history_raw"], catalogue),
    }
    for name, df in outputs.items():
        df.to_parquet(C.PROCESSED_DIR / f"{name}.parquet", index=False)
        print(f"wrote {name}: {len(df)} rows")
    review = outputs["dish_name_map"].query("needs_review")
    print(f"dish names needing review: {len(review)}")


if __name__ == "__main__":
    main()
