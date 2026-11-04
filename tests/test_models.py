"""Models: usual plan rule, VAE pieces, metrics, forecast service output and overrides."""

import numpy as np
import pandas as pd
import pytest
import torch

from feedforward import config as C
from feedforward.data.feature_registry import BANNED_INPUTS
from feedforward.models.baselines import usual_plan
from feedforward.models.cvae import CVAE, CVAEConfig, beta_at, sample_log_quantiles, vae_loss
from feedforward.models.metrics import coverage, pinball, round_portions, simulate_decision
from feedforward.models.prep import INPUT_COLUMNS
from feedforward.plugins.gan_extra_data import load_extra_rows
from feedforward.plugins.surplus_detector_stub import StubSurplusDetector

FINAL_READY = (C.MODELS_DIR / "final" / "cvae.pt").exists()


def test_usual_plan_is_two_week_average_plus_12_percent():
    d = pd.date_range("2026-01-01", periods=21)
    hist = pd.DataFrame({"date": d, "meal_slot": "lunch", "dish_id": "D1", "consumed_qty": 100})
    hist.loc[hist["date"] == "2026-01-08", "consumed_qty"] = 200
    hist.loc[hist["date"] == "2026-01-01", "consumed_qty"] = 300
    target = pd.DataFrame({"date": [pd.Timestamp("2026-01-15")], "meal_slot": ["lunch"], "dish_id": ["D1"]})
    assert usual_plan(hist, target).iloc[0] == pytest.approx((200 + 300) / 2 * 1.12)


def test_models_do_not_use_banned_inputs():
    assert not set(INPUT_COLUMNS) & BANNED_INPUTS


def test_vae_loss_zero_kl_and_mse_form():
    y, mean = torch.tensor([[1.0], [2.0]]), torch.tensor([[0.0], [2.0]])
    zeros = torch.zeros(2, 4)
    total, recon, kl, kl_dim = vae_loss(y, mean, torch.zeros(2, 1), zeros, zeros, beta=1.0)
    assert float(kl) == pytest.approx(0.0) and kl_dim.shape == (4,)
    assert float(recon) == pytest.approx(0.5 * (1.0 + 0.0) / 2)  # logvar 0: half the squared error
    # free bits: a collapsed latent is not rewarded below the floor
    t2, *_ = vae_loss(y, mean, torch.zeros(2, 1), zeros, zeros, beta=1.0, free_bits=0.1)
    assert float(t2) == pytest.approx(float(total) + 0.4)


def test_beta_annealing():
    assert beta_at(0, 20) == 0 and beta_at(10, 20) == 0.5 and beta_at(50, 20) == 1.0


@pytest.mark.parametrize("encoder", ["mlp", "gru"])
def test_cvae_shapes_and_sampling(encoder):
    cfg = CVAEConfig(encoder=encoder)
    model = CVAE(5, 7, cfg)
    y, dish, x = torch.randn(6, 1), torch.randint(0, 5, (6,)), torch.randn(6, 7)
    seq = torch.randn(6, 21, 5) if encoder == "gru" else None
    mean, dec_lv, mu, lv = model(y, dish, x, seq, torch.zeros(6, 1))
    assert mean.shape == (6, 1) and mu.shape == (6, cfg.latent_dim)
    mean.sum().backward()  # gradients reach the encoder through the reparameterisation trick
    assert model.enc_mu.weight.grad is not None
    q = sample_log_quantiles(model, dish, x, seq, torch.zeros(6, 1), 0.0, 1.0, (0.1, 0.5, 0.9), n_samples=50)
    assert (q[0.1] <= q[0.5]).all() and (q[0.5] <= q[0.9]).all()
    again = sample_log_quantiles(model, dish, x, seq, torch.zeros(6, 1), 0.0, 1.0, (0.5,), n_samples=50)
    assert np.allclose(again[0.5], q[0.5])  # seeded: same samples every time


def test_metrics_and_rounding():
    y = np.array([10.0, 20.0, 30.0])
    assert pinball(y, y + 5, 0.9) == pytest.approx(0.5)  # over-forecast costs (1 - q) * error
    assert coverage(y, y - 1, y + 1) == 1.0
    assert list(round_portions(np.array([47, 52, 101, 1234]))) == [45, 50, 100, 1230]
    sim = simulate_decision(pd.DataFrame({"demand_qty": [10, 10]}), np.array([12, 8]))
    assert sim["leftover"] == 2 and sim["shortage"] == 2


def test_surplus_stub_levels():
    d = StubSurplusDetector()
    assert d.assess(600, 470, 550) == "high" and d.assess(430, 370, 440) == "medium" and d.assess(400, 390, 450) == "low"


def test_extra_data_validation(tmp_path):
    bad = tmp_path / "x.csv"
    pd.DataFrame({"date": ["2026-01-01"], "demand_qty": [5]}).to_csv(bad, index=False)
    with pytest.raises(ValueError):
        load_extra_rows(bad)


@pytest.fixture(scope="module")
def service():
    from feedforward.models.forecast_service import ForecastService
    return ForecastService()


@pytest.mark.skipif(not FINAL_READY, reason="run: python -m feedforward.models.train --final")
def test_forecast_output_shape_and_order(service):
    r = service.forecast("2026-10-07", "lunch", n_samples=100)
    assert r["dishes"] and r["expected_attendance"] > 0
    for d in r["dishes"]:
        assert 0 <= d["p10"] <= d["p50"] <= d["p90"]
        assert d["recommended"] % 5 == 0 and d["surplus_risk"] in ("low", "medium", "high")
    assert r["totals"]["recommended"] == sum(d["recommended"] for d in r["dishes"])
    again = service.forecast("2026-10-07", "lunch", n_samples=100)
    assert again["totals"] == r["totals"]  # seeded, so the same question gives the same answer


@pytest.mark.skipif(not FINAL_READY, reason="run: python -m feedforward.models.train --final")
def test_overrides_and_errors(service):
    from feedforward.models.forecast_service import Overrides
    base = service.forecast("2026-10-07", "lunch", n_samples=100)
    up = service.forecast("2026-10-07", "lunch", overrides=Overrides(attendance_change_pct=15), n_samples=100)
    assert up["expected_attendance"] > base["expected_attendance"] and up["totals"]["p50"] > base["totals"]["p50"]
    assert up["overrides_applied"] == {"attendance_change_pct": 15}
    one = service.forecast("2026-10-07", "lunch", dish_ids=[base["dishes"][0]["dish_id"]], n_samples=100)
    assert len(one["dishes"]) == 1
    with pytest.raises(ValueError):
        service.forecast("2026-10-07", "brunch")
    with pytest.raises(ValueError):
        service.forecast("2026-10-07", "lunch", overrides=Overrides(weather_type="Snow"))


def test_two_short_trainings_with_the_same_seed_give_identical_losses():
    from feedforward.models.train import fit_bundle, load_panel
    panel = load_panel()
    small = panel[panel["date"] <= "2026-03-15"].copy()      # a small slice, trained for 2 epochs
    mask = small["split"] == "train"
    losses = []
    for _ in range(2):
        _, hist, _ = fit_bundle(small, mask, None, CVAEConfig(), fixed_epochs=2, log=False, seed=11)
        losses.append(hist["train_loss"])
    assert len(losses[0]) == 2 and losses[0] == losses[1]


def test_inventory_detector_levels_and_the_higher_of_two_rule():
    from feedforward.models.surplus_detector import InventoryAwareSurplusDetector
    d = InventoryAwareSurplusDetector()
    # demand risk alone (usual plan, most likely, high end)
    assert d.assess(400, 390, 450) == "low" and d.assess(500, 400, 550) == "medium" and d.assess(600, 470, 550) == "high"
    # inventory risk alone (demand is fine)
    assert d.assess(400, 390, 450, min_days_to_expiry=9, stock_cover_days=5, kg_expiring_within_3_days=0) == "low"
    assert d.assess(400, 390, 450, min_days_to_expiry=3, stock_cover_days=5, kg_expiring_within_3_days=20) == "medium"
    assert d.assess(400, 390, 450, min_days_to_expiry=1, stock_cover_days=5, kg_expiring_within_3_days=0) == "high"
    assert d.assess(400, 390, 450, min_days_to_expiry=9, stock_cover_days=0.5, kg_expiring_within_3_days=0) == "high"
    # the higher of the two wins, in both directions
    assert d.assess(500, 400, 550, min_days_to_expiry=1) == "high"                                    # demand medium, inventory high
    assert d.assess(600, 470, 550, min_days_to_expiry=9, stock_cover_days=9, kg_expiring_within_3_days=0) == "high"  # demand high, inventory low
    assert d.assess(500, 400, 550, min_days_to_expiry=3, kg_expiring_within_3_days=20) == "medium"   # both medium


def test_missing_inventory_data_uses_demand_risk_only():
    from feedforward.models.surplus_detector import InventoryAwareSurplusDetector
    d = InventoryAwareSurplusDetector()
    assert d.assess(400, 390, 450, min_days_to_expiry=None, stock_cover_days=None, kg_expiring_within_3_days=None) == "low"
    assert d.assess(600, 470, 550) == "high" and d.assess(500, 400, 550) == "medium"
    assert d.assess(0, 100, 200) == "low"                                                            # no usual plan


@pytest.mark.skipif(not FINAL_READY, reason="run: python -m feedforward.models.train --final")
def test_plan_says_whether_stock_data_was_used(service):
    inside = service.forecast(C.HISTORY_END, "lunch", n_samples=50)
    after = service.forecast("2026-10-07", "lunch", n_samples=50)
    assert inside["inventory_risk_available"] is True and after["inventory_risk_available"] is False
