"""Bulk import: turn an uploaded CSV into real daily log entries, reusing the same schemas and save path as
the Daily log form (feedforward.admin.schemas, store.save_day). One row is one (date, meal slot, dish or
ingredient); a CSV holds many days at once.

The expected columns match the matching export (GET /api/admin/export?table=...), so export a table, edit it
in a spreadsheet, and import it back. Column names are matched case-insensitively; extra columns are ignored.
One bad row is skipped and reported; it does not stop the rest of the file.
"""

import csv
import io
from datetime import date as Date

from pydantic import ValidationError

from feedforward.admin.schemas import AttendanceIn, DayContextIn, DaySaveIn, IngredientIn, KitchenRowIn

REQUIRED_COLUMNS = {
    "day_context": ["date"],
    "attendance": ["date", "meal_slot", "attendance"],
    "kitchen_log": ["date", "meal_slot", "dish_id", "prepared_qty"],
    "ingredient_usage": ["date", "ingredient", "used_kg"],
}


def _error_text(exc: ValidationError) -> str:
    first = exc.errors()[0]
    field = ".".join(str(p) for p in first["loc"]) or "value"
    return f"{field}: {first['msg']}"


def _blank(v: str | None) -> str | None:
    v = (v or "").strip()
    return v or None


def _truthy(v: str | None) -> bool:
    return (v or "").strip().lower() in ("1", "true", "yes", "y")


def _num(v: str | None) -> float | None:
    v = _blank(v)
    return None if v is None else float(v)


def _int(v: str | None) -> int | None:
    n = _num(v)
    return None if n is None else int(round(n))


def read_rows(text: str) -> list[dict]:
    """Parses the CSV text into dicts with lower cased, stripped column names."""
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise ValueError("The file is empty.")
    rename = {f: f.strip().lower() for f in reader.fieldnames}
    return [{rename.get(k, k): v for k, v in row.items() if k is not None} for row in reader]


def _build_day_context(row: dict) -> tuple[Date, DayContextIn]:
    d = Date.fromisoformat(row["date"].strip())
    ctx = DayContextIn(date=d, temp_max_c=_num(row.get("temp_max_c")), temp_min_c=_num(row.get("temp_min_c")),
                       weather_type=_blank(row.get("condition") or row.get("weather_type")),
                       special_day=_truthy(row.get("special_day")), special_day_type=_blank(row.get("special_day_type")),
                       special_day_name=_blank(row.get("special_day_name")), exam_week=_truthy(row.get("exam_week")),
                       exam_type=_blank(row.get("exam_type")), festival=_truthy(row.get("festival")),
                       festival_name=_blank(row.get("festival_name")), festival_scale=_blank(row.get("festival_scale")))
    return d, ctx


def _build_attendance(row: dict) -> tuple[Date, AttendanceIn]:
    d = Date.fromisoformat(row["date"].strip())
    a = AttendanceIn(meal_slot=row["meal_slot"].strip(), attendance=_int(row["attendance"]),
                      students_present=_int(row.get("students_present")))
    return d, a


def _build_kitchen(row: dict) -> tuple[Date, KitchenRowIn]:
    d = Date.fromisoformat(row["date"].strip())
    k = KitchenRowIn(meal_slot=row["meal_slot"].strip(), dish_id=row["dish_id"].strip(),
                      prepared_qty=_int(row["prepared_qty"]) or 0, topup_qty=_int(row.get("topup_qty")) or 0,
                      consumed_qty=_int(row.get("consumed_qty")), leftover_qty=_int(row.get("leftover_qty")),
                      ran_out_early=_truthy(row.get("ran_out_early")), unmet_qty=_int(row.get("unmet_qty")))
    return d, k


def _build_ingredient(row: dict) -> tuple[Date, IngredientIn]:
    d = Date.fromisoformat(row["date"].strip())
    i = IngredientIn(ingredient=row["ingredient"].strip(), used_kg=_num(row["used_kg"]) or 0)
    return d, i


BUILDERS = {"day_context": _build_day_context, "attendance": _build_attendance, "kitchen_log": _build_kitchen,
            "ingredient_usage": _build_ingredient}


def parse(table: str, text: str) -> tuple[dict[str, DaySaveIn], list[dict]]:
    """Parses a CSV for one table into one DaySaveIn per date (only that table's section filled in).

    Returns (entries by date, row errors). A row error is {"row": 1-based CSV line, "message": ...}; the row
    is skipped but the rest of the file is still processed.
    """
    if table not in BUILDERS:
        raise ValueError(f"Unknown table '{table}'. Choose one of {sorted(BUILDERS)}.")
    rows = read_rows(text)
    missing = [c for c in REQUIRED_COLUMNS[table] if not rows or c not in rows[0]]
    if missing:
        raise ValueError(f"The file is missing required column(s): {', '.join(missing)}.")
    build = BUILDERS[table]
    parts: dict[str, dict] = {}
    errors: list[dict] = []
    for i, row in enumerate(rows, start=2):  # row 1 is the header
        if not any((row or {}).values()):
            continue  # a blank line
        try:
            d, obj = build(row)
        except ValidationError as exc:
            errors.append({"row": i, "message": _error_text(exc)})
            continue
        except (ValueError, KeyError, TypeError) as exc:
            errors.append({"row": i, "message": str(exc)})
            continue
        p = parts.setdefault(str(d), {"context": None, "attendance": [], "kitchen": [], "ingredients": []})
        if table == "day_context":
            p["context"] = obj
        elif table == "attendance":
            p["attendance"].append(obj)
        elif table == "kitchen_log":
            p["kitchen"].append(obj)
        elif table == "ingredient_usage":
            p["ingredients"].append(obj)
    entries: dict[str, DaySaveIn] = {}
    for d, p in parts.items():
        try:
            entries[d] = DaySaveIn(date=Date.fromisoformat(d), **p)
        except ValidationError as exc:
            errors.append({"row": 0, "message": f"{d}: {_error_text(exc)}"})
    return entries, errors
