"""Admin daily log: PIN protected endpoints under /api/admin. Real entries are saved so later forecasts improve."""

import os
import secrets
from datetime import date as Date

import pandas as pd
from fastapi import APIRouter, Depends, Header, Query
from fastapi.responses import PlainTextResponse

from api import services
from api.deps import error, get_service, reload_service
from feedforward import config as C
from feedforward.admin import csv_import
from feedforward.admin.compare import forecast_vs_actual
from feedforward.admin.history import real_day_count
from feedforward.admin.schemas import CsvImportIn, DaySaveIn, DeleteIn, RecipeFillIn
from feedforward.admin.store import TABLES, get_store
from feedforward.admin.validation import check_future, sanity_warnings
from feedforward.data.features import menu_rows_for
from feedforward.models import week_view
from feedforward.models.forecast_service import ForecastService


def require_pin(x_admin_pin: str | None = Header(None)) -> None:
    """The admin PIN comes from ADMIN_PIN in .env and is sent in the X-Admin-Pin header."""
    pin = os.getenv("ADMIN_PIN", "").strip()
    if not pin or pin == "change-me":
        raise error(503, "The admin PIN is not set.", "Set ADMIN_PIN in the .env file (not the placeholder), then restart the server.")
    if not x_admin_pin or not secrets.compare_digest(x_admin_pin.encode(), pin.encode()):
        raise error(401, "The PIN is not correct.", "Type the PIN from the .env file and try again.")


router = APIRouter(prefix="/admin", dependencies=[Depends(require_pin)])


def _read(name: str) -> pd.DataFrame:
    return pd.read_parquet(C.PROCESSED_DIR / f"{name}.parquet")


def _records(df: pd.DataFrame) -> list[dict]:
    return df.drop(columns=["data_source", "deleted"], errors="ignore").to_dict(orient="records")


@router.post("/login")
def login() -> dict:
    """Checks the PIN (the dependency does the work)."""
    return {"ok": True, "today": str(services.today())}


@router.get("/menu")
def menu(date: Date) -> dict:
    """The dishes of each slot for a date (that weekday's menu) and what has already been saved for it."""
    rows = menu_rows_for(pd.DatetimeIndex([pd.Timestamp(date)]), _read("weekly_menu"))
    names = _read("dishes").set_index("dish_id")["dish_name"]
    slots = {s: [{"dish_id": d, "dish_name": names[d]} for d in rows.loc[rows["meal_slot"] == s, "dish_id"]] for s in C.MEAL_SLOTS}
    return {"date": str(date), "weekday": date.strftime("%A"), "today": str(services.today()), "slots": slots, "saved": _saved(date)}


def _saved(date: Date) -> dict:
    store = get_store()
    return {t: _records(store.read(t).loc[lambda df: df["date"] == str(date)]) for t in TABLES}


@router.get("/day")
def day(date: Date) -> dict:
    """What is saved for one date."""
    return _saved(date)


@router.post("/validate")
def validate(entry: DaySaveIn, svc: ForecastService = Depends(get_service)) -> dict:
    """Warnings about values that look like typos. Hard errors come back as a 422 before this runs."""
    check_future(entry, services.today())
    return {"warnings": sanity_warnings(entry, svc, _read("inventory_ingredients"))}


@router.post("/day")
def save(entry: DaySaveIn, svc: ForecastService = Depends(get_service)) -> dict:
    """Save (or update) one date. Warnings are returned but never block the save."""
    check_future(entry, services.today())
    warnings = sanity_warnings(entry, svc, _read("inventory_ingredients"))
    counts = get_store().save_day(entry)
    reload_service()                     # forecasts now use the new history and day information
    week_view._calendar_flags.cache_clear()
    return {"saved": counts, "warnings": warnings, "message": f"Saved {entry.date}. Forecasts now use this day."}


@router.get("/summary")
def summary() -> dict:
    """Quick status of the real data logged so far, and how close it is to being useful for retraining."""
    store = get_store()
    frames = {t: store.read(t) for t in TABLES}
    last_entered = max((f["entered_at"].max() for f in frames.values() if not f.empty), default=None)
    days = real_day_count(store)
    return {"real_days": days, "min_real_days": C.MIN_REAL_DAYS, "ready_for_retraining": days >= C.MIN_REAL_DAYS,
            "rows_by_table": {t: len(f) for t, f in frames.items()}, "last_entered_at": last_entered}


@router.get("/recent")
def recent(limit: int = Query(15, ge=1, le=100)) -> dict:
    """The most recently entered dates with how many rows each has."""
    store, frames = get_store(), []
    for table in TABLES:
        df = store.read(table)
        if not df.empty:
            frames.append(df[["date", "entered_at"]].assign(table=table))
    if not frames:
        return {"days": []}
    allrows = pd.concat(frames)
    out = []
    for d, g in allrows.groupby("date"):
        out.append({"date": d, "weekday": Date.fromisoformat(d).strftime("%A"), "entered_at": g["entered_at"].max(),
                    **{t: int((g["table"] == t).sum()) for t in TABLES}})
    return {"days": sorted(out, key=lambda r: r["entered_at"], reverse=True)[:limit]}


@router.delete("/entry")
def delete(body: DeleteIn) -> dict:
    """Soft delete: the rows stay in the file, marked deleted, and are ignored by forecasts."""
    key = {k: str(v) for k, v in body.model_dump().items() if k != "table" and v is not None}
    n = get_store().soft_delete(body.table, key)
    reload_service()
    return {"deleted_rows": n}


@router.get("/export", response_class=PlainTextResponse)
def export(table: str) -> PlainTextResponse:
    """One table as a CSV download."""
    if table not in TABLES:
        raise ValueError(f"Unknown table '{table}'. Choose one of {sorted(TABLES)}.")
    return PlainTextResponse(get_store().export_csv(table), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{table}.csv"'})


@router.post("/import")
def import_csv(body: CsvImportIn, svc: ForecastService = Depends(get_service)) -> dict:
    """Bulk import real entries for one table from CSV text (see feedforward.admin.csv_import for the expected
    columns, the same ones the matching export uses). Every date that parses is checked and saved exactly like
    the Daily log form; a bad row is skipped and reported rather than stopping the whole file."""
    entries, errors = csv_import.parse(body.table, body.csv_text)
    today = services.today()
    saved_dates, warnings = [], []
    ingredient_master = _read("inventory_ingredients")
    for d, entry in sorted(entries.items()):
        try:
            check_future(entry, today)
        except ValueError as exc:
            errors.append({"row": 0, "message": str(exc)})
            continue
        ws = sanity_warnings(entry, svc, ingredient_master)
        get_store().save_day(entry)
        saved_dates.append(d)
        warnings += [{"date": d, **w} for w in ws]
    if saved_dates:
        reload_service()
        week_view._calendar_flags.cache_clear()
    return {"table": body.table, "dates_saved": len(saved_dates), "dates": saved_dates, "row_errors": errors,
            "warnings": warnings, "message": f"Imported {len(saved_dates)} day(s) into {body.table}."
            + (f" {len(errors)} row(s) could not be used." if errors else "")}


@router.post("/fill-recipes")
def fill_recipes(body: RecipeFillIn) -> dict:
    """Ingredient kilograms from prepared portions times the recipe grams (the admin can edit the result)."""
    recipes = _read("recipes")
    totals: dict[str, float] = {}
    for r in body.rows:
        qty = float(r.get("prepared_qty") or 0)
        for _, row in recipes[recipes["dish_id"] == r.get("dish_id")].iterrows():
            totals[row["ingredient"]] = totals.get(row["ingredient"], 0.0) + qty * row["qty_g_per_portion"] / 1000
    return {"ingredients": [{"ingredient": k, "used_kg": round(v, 1)} for k, v in sorted(totals.items())]}


@router.get("/forecast-vs-actual")
def compare() -> dict:
    """Approved forecasts next to the demand that was logged afterwards."""
    return forecast_vs_actual()
