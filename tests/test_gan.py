"""Rare event GAN: training table, WGAN-GP, synthetic rows, the file train.py reads and the sample weight path."""

import numpy as np
import pandas as pd
import pytest
import torch

from feedforward import config as C
from feedforward.data import gan_data as GD
from feedforward.data.feature_registry import BANNED_INPUTS
from feedforward.models import gan as G
from feedforward.models.train_gan import train
from feedforward.plugins import gan_extra_data as X

pytestmark = pytest.mark.skipif(not (C.TIMESERIES_DIR / "panel.parquet").exists(), reason="run the preprocessing steps first")


@pytest.fixture(scope="module")
def table():
    return GD.build_table()


def test_gan_table_uses_only_the_train_period_and_no_leakage(table):
    t, log = table
    assert t["date"].max() <= pd.Timestamp(C.TRAIN_END)
    assert log["last_date"] <= C.TRAIN_END
    scaler = GD.GanScaler().fit(t)
    assert not set(scaler.columns) & (BANNED_INPUTS | GD.LEAKAGE_COLUMNS)
    assert set(t["event_type"]) <= set(GD.EVENT_TYPES) and (t["event_type"] != "normal").any()
    assert len(t) == log["table_rows"] == log["rare_rows"] + log["normal_rows"]


def test_gan_table_shapes_and_scaler_round_trip(table, tmp_path):
    t, _ = table
    scaler = GD.GanScaler().fit(t)
    cond, y = scaler.conditions(t), scaler.scale_target(t["demand_qty"])
    assert cond.shape == (len(t), len(scaler.columns)) and y.shape == (len(t), 1)
    assert np.isfinite(cond).all() and abs(float(y.mean())) < 1e-3
    scaler.save(tmp_path)
    again = GD.GanScaler.load(tmp_path)
    assert np.allclose(again.conditions(t), cond)
    assert np.allclose(again.to_demand(y.ravel()), t["demand_qty"].to_numpy(), atol=1)  # back to portions (rounded)


def test_table_is_the_same_every_time():
    a, _ = GD.build_table(seed=1)
    b, _ = GD.build_table(seed=1)
    assert a[["date", "meal_slot", "dish_id"]].equals(b[["date", "meal_slot", "dish_id"]])


def test_networks_shapes_and_finite_gradient_penalty():
    torch.manual_seed(0)
    gen, critic = G.Generator(10), G.Critic(10)
    cond = torch.randn(16, 10)
    fake = gen(torch.randn(16, G.NOISE_DIM), cond)
    assert fake.shape == (16, 1) and critic(fake, cond).shape == (16, 1)
    gp = G.gradient_penalty(critic, torch.randn(16, 1), fake.detach(), cond)
    assert torch.isfinite(gp) and gp >= 0
    assert torch.isfinite(G.critic_loss(critic, torch.randn(16, 1), fake.detach(), cond))


def test_same_seed_gives_identical_losses():
    rng = np.random.default_rng(0)
    cond = rng.normal(size=(300, 6)).astype(np.float32)
    y = rng.normal(size=300).astype(np.float32)
    events = np.array(["festival", "normal"] * 150)
    runs = [train(cond, y, events, epochs=2, seed=7, log=False, check_every=1)[1] for _ in range(2)]
    assert runs[0]["history"] == runs[1]["history"]


def _rows(**over):
    base = {"date": pd.Timestamp("2026-01-05"), "meal_slot": "lunch", "dish_id": "D1", "category": "rice",
            "demand_qty": 1000, "expected_attendance": 3000}
    return pd.DataFrame([base | over])


def test_validate_rejects_bad_rows_and_counts_reasons():
    real = pd.concat([_rows(demand_qty=900), _rows(demand_qty=1100, date=pd.Timestamp("2026-01-06"))], ignore_index=True)
    rows = pd.concat([_rows(demand_qty=1000, date=pd.Timestamp("2026-02-02")),     # fine
                      _rows(demand_qty=-5, date=pd.Timestamp("2026-02-03")),         # below zero
                      _rows(demand_qty=1500, date=pd.Timestamp("2026-02-04")),       # above 1.3 x dish max (1100)
                      _rows(demand_qty=1000, date=pd.Timestamp("2026-02-05"), expected_attendance=100),  # rate far above real
                      _rows(demand_qty=900)],                                          # same as a real row
                     ignore_index=True)
    kept, counts = X.validate(rows, real)
    assert len(kept) == 1 and kept["demand_qty"].iloc[0] == 1000
    assert counts == {"below_zero": 1, "above_dish_max": 1, "outside_category_range": 1, "duplicate_of_real": 1}


@pytest.fixture(scope="module")
def tiny_gan(table, tmp_path_factory):
    """A 2-epoch generator in a temp folder (quality does not matter here, the plumbing does)."""
    folder = tmp_path_factory.mktemp("gan")
    t, _ = table
    scaler = GD.GanScaler().fit(t)
    gen, _ = train(scaler.conditions(t), scaler.scale_target(t["demand_qty"]).ravel(), t["event_type"].to_numpy(),
                   epochs=2, seed=3, log=False)
    scaler.save(folder)
    torch.save({"state": gen.state_dict(), "n_cond": len(scaler.columns)}, folder / "generator.pt")
    return folder


def test_generated_file_is_written_labelled_and_readable_by_train(tiny_gan, tmp_path):
    rows, real = X.generate(n_per_condition=1, folder=tiny_gan)
    kept, rejected = X.validate(rows, real)
    assert len(rows) == len(kept) + sum(rejected.values()) and len(kept) > 0
    path = X.write_extra_rows(kept, tmp_path / "extra_rows.csv")
    extra = X.load_extra_rows(path, weight=0.3)
    assert len(extra) == len(kept) and (extra["synthetic"] == 1).all() and (extra["source"] == "gan").all()
    assert (extra["sample_weight"] == 0.3).all() and (extra["demand_qty"] >= 0).all()


def test_synthetic_rows_never_reach_validation_or_test(tiny_gan, tmp_path):
    from feedforward.models.train import usable
    rows, real = X.generate(n_per_condition=1, folder=tiny_gan)
    kept, _ = X.validate(rows, real)
    extra = X.load_extra_rows(X.write_extra_rows(kept, tmp_path / "e.csv"))
    panel = pd.read_parquet(C.TIMESERIES_DIR / "panel.parquet")
    held_out = panel[panel["split"].isin(["val", "test"]) & usable(panel, True)]
    assert not (extra["date"].between(pd.Timestamp(C.VAL_START), pd.Timestamp(C.TEST_END))).any()
    keys = set(zip(held_out["date"], held_out["meal_slot"], held_out["dish_id"], strict=True))
    assert not keys & set(zip(extra["date"], extra["meal_slot"], extra["dish_id"], strict=True))


def test_rows_dated_in_validation_or_test_are_refused(tmp_path):
    rows = pd.DataFrame({c: [1] for c in X.REQUIRED_COLUMNS}).assign(date="2026-07-01")
    path = tmp_path / "late.csv"
    rows.to_csv(path, index=False)
    with pytest.raises(ValueError, match="validation or test"):
        X.load_extra_rows(path)


def test_sample_weight_reaches_the_training_tensors(tiny_gan, tmp_path):
    from feedforward.models.attendance import add_expected_attendance
    from feedforward.models.prep import FeatureTransformer
    from feedforward.models.train import to_tensors, usable
    rows, real = X.generate(n_per_condition=1, folder=tiny_gan)
    kept, _ = X.validate(rows, real)
    extra = X.load_extra_rows(X.write_extra_rows(kept, tmp_path / "w.csv"), weight=0.3)
    panel = pd.read_parquet(C.TIMESERIES_DIR / "panel.parquet").reset_index(drop=True)
    panel, _ = add_expected_attendance(panel, panel["split"] == "train")
    train_df = panel[(panel["split"] == "train") & usable(panel, True)]
    both = pd.concat([train_df.assign(sample_weight=1.0), extra], ignore_index=True)
    tensors = to_tensors(both, FeatureTransformer().fit(both), 0.0, 1.0, 0.0)
    w = tensors["weight"]
    assert torch.isclose(w[:len(train_df)], torch.tensor(1.0)).all() and torch.isclose(w[len(train_df):], torch.tensor(0.3)).all()
