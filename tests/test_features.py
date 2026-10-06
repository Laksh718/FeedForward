"""Cleaning against ground truth, leakage, splits, lags and model inputs."""

import numpy as np
import pandas as pd
import pytest

from feedforward import config as C
from feedforward.data.cleaning import clean_kitchen, compare_with_truth
from feedforward.data.feature_registry import BANNED_INPUTS, FEATURE_COLUMNS, LAGS
from feedforward.data.features import add_weather_noise, lag_features, menu_rows_for
from feedforward.data.loaders import load_table
from feedforward.data.preprocess import normalise_ids
from feedforward.data.splits import assign_split, regime, rolling_origin_folds
from feedforward.data.timeseries import build_panel, build_windows, load_clean_history


@pytest.fixture(scope="module")
def dishes():
    return pd.read_parquet(C.PROCESSED_DIR / "dishes.parquet")


@pytest.fixture(scope="module")
def panel(dishes):
    menu = pd.read_parquet(C.PROCESSED_DIR / "weekly_menu.parquet")
    return build_panel(load_clean_history(), dishes, menu)


def test_cleaning_matches_ground_truth():
    clean, log = clean_kitchen(load_table("kitchen_history_raw"), normalise_ids(load_table("dishes")))
    assert log["duplicates_dropped"] == 15 and log["consistency_violations"] == 0
    diff = compare_with_truth(clean, load_table("kitchen_history"))
    assert diff["same_row_count"]
    assert set(diff["columns_with_differences"]) <= {"leftover_kg"}  # 0.01 kg rounding only
    assert diff["columns_with_differences"].get("leftover_kg", 0) <= 2


def test_no_banned_column_is_a_feature():
    assert not set(FEATURE_COLUMNS) & BANNED_INPUTS
    assert len(FEATURE_COLUMNS) == len(set(FEATURE_COLUMNS))


def test_no_nan_in_model_inputs(panel):
    assert not panel[FEATURE_COLUMNS].isna().any().any()
    assert len(panel) == 15745


def test_menu_rule_reproduces_history(panel):
    hist = load_clean_history()
    menu = pd.read_parquet(C.PROCESSED_DIR / "weekly_menu.parquet")
    rows = menu_rows_for(pd.DatetimeIndex(sorted(hist["date"].unique())), menu)
    key = ["date", "meal_slot", "dish_id"]
    assert len(rows) == len(hist) and rows.merge(hist[key], on=key).shape[0] == len(hist)


def test_splits_chronological_and_disjoint(panel):
    ranges = {s: (g["date"].min(), g["date"].max()) for s, g in panel.groupby("split")}
    assert ranges["train"][1] < ranges["val"][0] <= ranges["val"][1] < ranges["test"][0]
    assert panel.loc[panel["split"] == "train", "date"].nunique() == 255
    assert panel.loc[panel["split"] == "val", "date"].nunique() == 55
    assert panel.loc[panel["split"] == "test", "date"].nunique() == 55
    assert (assign_split(pd.Series(pd.to_datetime(["2026-06-17", "2026-06-18"]))) == ["train", "val"]).all()


def test_rolling_origin_folds():
    folds = rolling_origin_folds()
    assert len(folds) == 4 and folds[-1]["test_end"] == pd.Timestamp(C.HISTORY_END)
    for a, b in zip(folds, folds[1:], strict=False):
        assert a["test_end"] + pd.Timedelta(days=1) == b["test_start"]
        assert a["train_end"] < a["test_start"]


def test_lags_use_only_old_values():
    d = pd.date_range("2026-01-01", periods=30)
    hist = pd.DataFrame({"date": d, "meal_slot": "lunch", "dish_id": "D1", "consumed_qty": np.arange(30) * 10,
                         "unmet_qty": 0, "attendance": 100, "prepared_qty": 500, "topup_qty": 0, "leftover_qty": 5})
    target = hist[hist["date"] == "2026-01-25"]
    out = lag_features(hist, target).iloc[0]
    assert out["demand_lag_7"] == 17 * 10 and out["demand_lag_14"] == 10 * 10 and out["demand_lag_21"] == 3 * 10
    assert out["demand_mean3"] == pytest.approx(np.mean([170, 100, 30]))
    assert min(LAGS) >= 7


def test_future_values_do_not_change_features(panel, dishes):
    hist = load_clean_history()
    cutoff = pd.Timestamp("2026-07-01")
    menu = pd.read_parquet(C.PROCESSED_DIR / "weekly_menu.parquet")
    short = build_panel(hist[hist["date"] < cutoff + pd.Timedelta(days=7)], dishes, menu)
    a = short[short["date"] < cutoff].set_index(["date", "meal_slot", "dish_id"])[FEATURE_COLUMNS]
    b = panel[panel["date"] < cutoff].set_index(["date", "meal_slot", "dish_id"])[FEATURE_COLUMNS]
    pd.testing.assert_frame_equal(a.sort_index(), b.sort_index())


def test_windows_shape_and_alignment(panel):
    arrays, index = build_windows(panel, load_clean_history())
    assert arrays["x_seq"].shape == (len(panel), C.SEQ_LOOKBACK, 5)
    assert not np.isnan(arrays["x_seq"]).any() and len(index) == len(panel)
    # last window step is 7 days before the target: its log demand equals log1p(demand_lag_7)
    served = panel["has_lag_7"].to_numpy() == 1
    last = arrays["x_seq"][served, -1, 0]
    assert np.allclose(np.expm1(last), panel.loc[served, "demand_lag_7"], atol=1e-2)


def test_regimes_and_weather_noise(panel):
    assert set(panel["regime"]) <= {"normal", "exam", "holiday_festival", "vacation", "rainy"}
    one = panel.drop_duplicates("date")
    noisy = add_weather_noise(one, np.random.default_rng(0))
    assert (noisy["temp_max_c"] != one["temp_max_c"]).any() and noisy["rain_level"].between(0, 3).all()
    assert regime(one).equals(one["regime"])
