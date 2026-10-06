"""Storage of real daily entries. LogStore is the interface; CsvLogStore writes CSV files in data_store/admin_logs/.

A database can replace CsvLogStore later without touching the API or the form: implement the same methods.
Column names mirror the dataset tables so the logs can be appended to the history. Every row also carries
data_source (admin_real), entered_at, entered_by and deleted (soft delete).
"""

import threading
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

import pandas as pd

from feedforward import config as C
from feedforward.admin.schemas import DaySaveIn

DATA_SOURCE = "admin_real"
META = ["data_source", "entered_at", "entered_by", "deleted"]
TABLES: dict[str, dict] = {
    "day_context": {"key": ["date"], "columns": [
        "date", "day_of_week", "temp_max_c", "temp_min_c", "temp_mean_c", "condition", "rain_level", "special_day", "special_day_type",
        "special_day_name", "exam_week", "exam_type", "festival", "festival_name", "festival_scale"]},
    "attendance": {"key": ["date", "meal_slot"], "columns": ["date", "day_of_week", "meal_slot", "attendance", "students_present"]},
    "kitchen_log": {"key": ["date", "meal_slot", "dish_id"], "columns": [
        "date", "day_of_week", "meal_slot", "dish_id", "prepared_qty", "topup_qty", "consumed_qty", "unmet_qty", "leftover_qty",
        "ran_out_early"]},
    "ingredient_usage": {"key": ["date", "ingredient"], "columns": ["date", "day_of_week", "ingredient", "used_kg"]},
}


class LogStore(ABC):
    """What the API needs from any storage."""

    @abstractmethod
    def save_day(self, entry: DaySaveIn) -> dict[str, int]:
        """Insert or update the rows of one date. Returns how many rows were written per table."""

    @abstractmethod
    def read(self, table: str, include_deleted: bool = False) -> pd.DataFrame:
        """All rows of a table."""

    @abstractmethod
    def soft_delete(self, table: str, key: dict) -> int:
        """Mark matching rows deleted. Returns the number of rows marked."""

    @abstractmethod
    def export_csv(self, table: str) -> str:
        """The table as CSV text (deleted rows left out)."""


class CsvLogStore(LogStore):
    """CSV files, one per table, safe for one writer at a time."""

    def __init__(self, folder: Path | None = None) -> None:
        self.folder = folder or C.ADMIN_LOG_DIR
        self._lock = threading.Lock()

    def _path(self, table: str) -> Path:
        return self.folder / f"{table}.csv"

    def read(self, table: str, include_deleted: bool = False) -> pd.DataFrame:
        cols = TABLES[table]["columns"] + META
        path = self._path(table)
        if not path.exists():
            return pd.DataFrame(columns=cols)
        df = pd.read_csv(path, encoding="utf-8", keep_default_na=False)
        for c in cols:
            if c not in df:
                df[c] = ""
        df["deleted"] = pd.to_numeric(df["deleted"], errors="coerce").fillna(0).astype(int)
        return df if include_deleted else df[df["deleted"] == 0].reset_index(drop=True)

    def _upsert(self, table: str, rows: list[dict]) -> int:
        """Write rows, replacing rows with the same key. Rows of the same date that are not in `rows` are marked deleted,
        so saving a date again replaces that date's section instead of leaving old rows behind."""
        if not rows:
            return 0
        key, cols = TABLES[table]["key"], TABLES[table]["columns"] + META
        new = pd.DataFrame(rows, columns=cols)
        old = self.read(table, include_deleted=True)
        same_day = old["date"].astype(str) == str(rows[0]["date"])
        kept = set(map(tuple, new[key].astype(str).to_numpy()))
        stale = same_day & ~old[key].astype(str).apply(tuple, axis=1).isin(kept)
        old.loc[stale, "deleted"] = 1
        merged = pd.concat([old.astype(str), new.astype(str)], ignore_index=True).drop_duplicates(key, keep="last")
        self.folder.mkdir(parents=True, exist_ok=True)
        merged.sort_values(key).to_csv(self._path(table), index=False, encoding="utf-8")
        return len(rows)

    def save_day(self, entry: DaySaveIn) -> dict[str, int]:
        meta = {"data_source": DATA_SOURCE, "entered_at": datetime.now().isoformat(timespec="seconds"),
                "entered_by": entry.entered_by or "", "deleted": 0}
        d, dow = str(entry.date), entry.date.strftime("%A")
        base = {"date": d, "day_of_week": dow, **meta}
        counts = {}
        with self._lock:
            ctx = entry.context
            ctx_rows = []
            if ctx:
                temps = [t for t in (ctx.temp_max_c, ctx.temp_min_c) if t is not None]
                from feedforward.data.weather_types import WEATHER_TYPE_RAIN_LEVEL
                ctx_rows = [{**base, "temp_max_c": ctx.temp_max_c, "temp_min_c": ctx.temp_min_c,
                             "temp_mean_c": round(sum(temps) / len(temps), 1) if len(temps) == 2 else "",
                             "condition": ctx.weather_type or "",
                             "rain_level": WEATHER_TYPE_RAIN_LEVEL.get(ctx.weather_type, "") if ctx.weather_type else "",
                             "special_day": int(ctx.special_day), "special_day_type": ctx.special_day_type or "",
                             "special_day_name": ctx.special_day_name or "", "exam_week": int(ctx.exam_week),
                             "exam_type": ctx.exam_type or "", "festival": int(ctx.festival),
                             "festival_name": ctx.festival_name or "", "festival_scale": ctx.festival_scale or ""}]
            counts["day_context"] = self._upsert("day_context", ctx_rows)
            counts["attendance"] = self._upsert("attendance", [
                {**base, "meal_slot": a.meal_slot, "attendance": a.attendance,
                 "students_present": "" if a.students_present is None else a.students_present} for a in entry.attendance])
            counts["kitchen_log"] = self._upsert("kitchen_log", [
                {**base, "meal_slot": k.meal_slot, "dish_id": k.dish_id, "prepared_qty": k.prepared_qty, "topup_qty": k.topup_qty,
                 "consumed_qty": "" if k.consumed_qty is None else k.consumed_qty,
                 "unmet_qty": k.unmet_qty or 0, "leftover_qty": "" if k.leftover_qty is None else k.leftover_qty,
                 "ran_out_early": int(k.ran_out_early)} for k in entry.kitchen])
            counts["ingredient_usage"] = self._upsert("ingredient_usage", [
                {**base, "ingredient": i.ingredient, "used_kg": i.used_kg} for i in entry.ingredients])
        return counts

    def soft_delete(self, table: str, key: dict) -> int:
        with self._lock:
            df = self.read(table, include_deleted=True)
            if df.empty:
                return 0
            mask = pd.Series(True, index=df.index)
            for col, value in key.items():
                mask &= df[col].astype(str) == str(value)
            mask &= df["deleted"] == 0
            df.loc[mask, "deleted"] = 1
            df.to_csv(self._path(table), index=False, encoding="utf-8")
            return int(mask.sum())

    def export_csv(self, table: str) -> str:
        return self.read(table).to_csv(index=False)


def get_store() -> LogStore:
    """The storage in use. Replace this one line to switch to a database."""
    return CsvLogStore()
