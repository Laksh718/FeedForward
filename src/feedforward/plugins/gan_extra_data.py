"""Rare event GAN: make synthetic rows, check them, and write the file that train.py --extra-data reads.

python -m feedforward.models.train_gan                                                     (once: trains the GAN)
python -m feedforward.plugins.gan_extra_data --generate --out artifacts/gan/extra_rows.csv  (makes the rows)
python -m feedforward.models.train --extra-data artifacts/gan/extra_rows.csv                (trains the VAE with them)

How a row is made: take a real feature row for a rare condition (a festival, holiday, exam week or heavy rain day
from the train period, or an upcoming one from data_store/calendar_future.csv), ask the GAN for a demand under that
condition, and keep the rest of the row as it is. Synthetic rows are labelled (synthetic = 1, source = gan), are
down weighted, and are never used for validation, calibration or testing.
"""

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd
import torch

from feedforward import config as C
from feedforward.data.feature_registry import FEATURE_COLUMNS
from feedforward.data.features import build_features, menu_rows_for
from feedforward.data.gan_data import GAN_DIR, RARE_TYPES, GanScaler, load_train_panel, with_gan_columns
from feedforward.data.timeseries import load_clean_history
from feedforward.models.gan import Generator, sample

REQUIRED_COLUMNS = ["date", "meal_slot", "dish_id", "dish_idx", "is_core", "demand_qty", "expected_attendance",
                    *FEATURE_COLUMNS]
LABEL_COLUMNS = ["synthetic", "source", "event_type"]
MAX_ABOVE_DISH_MAX = 1.3      # a dish never gets more than 1.3 times its largest real demand
RATE_MARGIN = (0.7, 1.3)      # category range: 0.7 times the lowest to 1.3 times the highest real demand per attendee
REASONS = ("below_zero", "above_dish_max", "outside_category_range", "duplicate_of_real")


def load_extra_rows(path: Path, weight: float = C.EXTRA_DATA_WEIGHT) -> pd.DataFrame:
    """Read and validate a synthetic rows file for train.py. Raises ValueError if it is not usable."""
    path = Path(path)
    df = pd.read_parquet(path) if path.suffix == ".parquet" else pd.read_csv(path, parse_dates=["date"])
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"{path.name}: missing columns {missing}")
    if df[REQUIRED_COLUMNS].isna().any().any() or (df["demand_qty"] < 0).any():
        raise ValueError(f"{path.name}: NaN or negative demand in synthetic rows")
    held_out = (df["date"] >= pd.Timestamp(C.VAL_START)) & (df["date"] <= pd.Timestamp(C.TEST_END))
    if held_out.any():
        raise ValueError(f"{path.name}: {int(held_out.sum())} synthetic rows are dated inside the validation or test period")
    return df.assign(is_synthetic=True, sample_weight=weight)


def load_generator(folder: Path = GAN_DIR) -> tuple[Generator, GanScaler]:
    """The trained generator and its scaler (made by feedforward.models.train_gan)."""
    saved = torch.load(Path(folder) / "generator.pt")
    gen = Generator(saved["n_cond"])
    gen.load_state_dict(saved["state"])
    return gen, GanScaler.load(Path(folder))


def condition_templates(train: pd.DataFrame, dishes: pd.DataFrame, att, include_future: bool = True) -> pd.DataFrame:
    """One real feature row per rare condition: the latest train row of each (event, slot, dish), plus upcoming rare days."""
    rare = train[train["event_type"].isin(RARE_TYPES)]
    seen = rare.sort_values("date").groupby(["event_type", "meal_slot", "dish_id"]).tail(1)
    parts = [seen.assign(origin="train")]
    if include_future:
        dates = pd.DatetimeIndex(pd.read_csv(C.CALENDAR_FUTURE_CSV, parse_dates=["date"])["date"])
        menu = pd.read_parquet(C.PROCESSED_DIR / "weekly_menu.parquet")
        feats = build_features(menu_rows_for(dates, menu), load_clean_history(), dishes)
        feats = feats[(feats["is_core"] == 1) & (feats["n_lags"] > 0)].reset_index(drop=True)
        feats["expected_attendance"] = att.predict(feats)
        feats = with_gan_columns(feats, dishes)
        parts.append(feats[feats["event_type"].isin(("festival", "holiday", "exam_week"))].assign(origin="calendar_future"))
    return pd.concat(parts, ignore_index=True)


def generate(n_per_condition: int = 5, seed: int = C.SEED, folder: Path = GAN_DIR, include_future: bool = True
             ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Draw synthetic demand for every rare condition. Returns the rows (not yet checked) and the real train rows."""
    train, dishes, att = load_train_panel()
    gen, scaler = load_generator(folder)
    templates = condition_templates(train, dishes, att, include_future)
    cond = torch.from_numpy(scaler.conditions(templates))
    frames = []
    for k in range(n_per_condition):
        scaled = sample(gen, cond, seed + k).numpy()
        log_y = scaler.target.inverse_transform(scaled.reshape(-1, 1)).ravel()
        frames.append(templates.assign(demand_qty=np.round(np.expm1(log_y)).astype(int), draw=k))
    rows = pd.concat(frames, ignore_index=True).assign(synthetic=1, source="gan")
    return rows, train


def validate(rows: pd.DataFrame, real: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Keep plausible rows. Returns the kept rows and how many were rejected for each reason (first failing rule counts)."""
    dish_max = real.groupby("dish_id")["demand_qty"].max()
    rate = real["demand_qty"] / real["expected_attendance"]
    cat_rate = rate.groupby(real["category"]).agg(["min", "max"])
    real_keys = set(zip(real["date"], real["meal_slot"], real["dish_id"], real["demand_qty"], strict=True))
    d_rate = rows["demand_qty"] / rows["expected_attendance"]
    lo = rows["category"].map(cat_rate["min"]) * RATE_MARGIN[0]
    hi = rows["category"].map(cat_rate["max"]) * RATE_MARGIN[1]
    checks = {
        "below_zero": rows["demand_qty"] < 0,
        "above_dish_max": rows["demand_qty"] > MAX_ABOVE_DISH_MAX * rows["dish_id"].map(dish_max),
        "outside_category_range": ~((d_rate >= lo) & (d_rate <= hi)),
        "duplicate_of_real": pd.Series([k in real_keys for k in zip(rows["date"], rows["meal_slot"], rows["dish_id"],
                                                                     rows["demand_qty"], strict=True)], index=rows.index),
    }
    rejected, counts = pd.Series(False, index=rows.index), {}
    for reason in REASONS:
        hit = checks[reason] & ~rejected
        counts[reason] = int(hit.sum())
        rejected |= hit
    return rows[~rejected].copy(), counts


def write_extra_rows(kept: pd.DataFrame, out: Path) -> Path:
    """Write the kept rows in the format train.py --extra-data reads (csv)."""
    out = Path(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = [*REQUIRED_COLUMNS, *LABEL_COLUMNS]
    kept.sort_values(["date", "meal_slot", "dish_id"])[cols].to_csv(out, index=False, date_format="%Y-%m-%d")
    return out


def main() -> None:
    """Command line entry point."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--generate", action="store_true", help="make synthetic rows and write them to --out")
    ap.add_argument("--out", default=str(GAN_DIR / "extra_rows.csv"))
    ap.add_argument("--n", type=int, default=5, help="samples per rare condition")
    ap.add_argument("--seed", type=int, default=C.SEED)
    ap.add_argument("--no-future", action="store_true", help="only use conditions seen in the train period")
    args = ap.parse_args()
    if not args.generate:
        ap.error("add --generate")
    rows, real = generate(args.n, args.seed, include_future=not args.no_future)
    kept, rejected = validate(rows, real)
    write_extra_rows(kept, Path(args.out))
    counts = {"generated": len(rows), "rejected": rejected, "rejected_total": sum(rejected.values()), "kept": len(kept),
              "kept_by_event": kept["event_type"].value_counts().to_dict(), "samples_per_condition": args.n}
    print(json.dumps(counts, indent=2))
    (Path(args.out).parent / "generation_counts.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
    from feedforward.models.gan_report import write_gan_report
    write_gan_report(kept, real, counts)
    print(f"wrote {args.out}, reports/gan_report.md and reports/gan/")


if __name__ == "__main__":
    main()
