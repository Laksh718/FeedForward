"""Train the demand models.

python -m feedforward.models.train                  development run: train on train, early stop on validation
python -m feedforward.models.train --final          retrain on train + validation with the chosen epochs
python -m feedforward.models.train --encoder gru    optional GRU experiment (compare with the default MLP)
python -m feedforward.models.train --extra-data F   add synthetic rare event rows from the GAN (teammate)
"""

import argparse
import json

import numpy as np
import pandas as pd
import torch

from feedforward import config as C
from feedforward.models.attendance import add_expected_attendance
from feedforward.models.baselines import GBMQuantile, SupportRule
from feedforward.models.bundle import ModelBundle
from feedforward.models.cvae import CVAE, CVAEConfig, train_cvae
from feedforward.models.prep import INPUT_COLUMNS, FeatureTransformer, noisy_weather_rows

DEV_DIR, FINAL_DIR = C.MODELS_DIR / "dev", C.MODELS_DIR / "final"


def load_panel() -> pd.DataFrame:
    """The model panel (features, target, split, regime) built by data.timeseries."""
    return pd.read_parquet(C.TIMESERIES_DIR / "panel.parquet")


def load_windows() -> np.ndarray:
    """Sequence windows aligned row by row with the panel (used by the GRU experiment)."""
    return np.load(C.TIMESERIES_DIR / "windows.npz")["x_seq"]


def usable(df: pd.DataFrame, core: bool) -> pd.Series:
    """Rows of core (or support) dishes that have some history (warm up rows are left out)."""
    return (df["is_core"] == int(core)) & (df["n_lags"] > 0)


def to_tensors(df: pd.DataFrame, tf: FeatureTransformer, y_mean: float, y_std: float, shift: float,
               seq: np.ndarray | None = None, x: np.ndarray | None = None) -> dict:
    """Tensors for training or validation: scaled target, dish index, numeric inputs, optional sequences."""
    y = (np.log1p(df["demand_qty"].to_numpy()) - y_mean) / y_std
    out = {"y": torch.tensor(y, dtype=torch.float32).unsqueeze(1),
           "dish": torch.tensor(df["dish_idx"].to_numpy(), dtype=torch.long),
           "x": torch.from_numpy(tf.transform(df) if x is None else x),
           "off": torch.tensor((np.log(df["expected_attendance"].to_numpy()) + shift - y_mean) / y_std,
                               dtype=torch.float32).unsqueeze(1)}
    if seq is not None:
        out["seq"] = torch.from_numpy(seq)
    if "sample_weight" in df:
        out["weight"] = torch.tensor(df["sample_weight"].fillna(1.0).to_numpy(), dtype=torch.float32)
    return out


def fit_bundle(panel: pd.DataFrame, fit_mask: pd.Series, val_mask: pd.Series | None, cfg: CVAEConfig,
               seq: np.ndarray | None = None, extra: pd.DataFrame | None = None, fixed_epochs: int | None = None,
               spread_factor: float = 1.0, log: bool = True) -> tuple[ModelBundle, dict, pd.DataFrame]:
    """Fit attendance, CVAE, GBM baseline and support rule. Returns the bundle, training history, panel+attendance."""
    panel = panel.reset_index(drop=True)
    panel, att = add_expected_attendance(panel, fit_mask)
    train_df = panel[fit_mask & usable(panel, True)]
    train_seq = seq[train_df.index] if seq is not None else None
    if extra is not None:
        train_df = pd.concat([train_df.assign(sample_weight=1.0), extra], ignore_index=True)
    tf = FeatureTransformer().fit(train_df)
    log_y = np.log1p(train_df["demand_qty"].to_numpy())
    y_mean, y_std = float(log_y.mean()), float(log_y.std())
    shift = float(np.mean(log_y - np.log(train_df["expected_attendance"].to_numpy())))  # typical log rate
    n_dishes = int(panel["dish_idx"].max()) + 1
    model = CVAE(n_dishes, len(INPUT_COLUMNS), cfg)
    rng_seed = C.SEED

    def make_train(epoch: int) -> dict:
        noisy = noisy_weather_rows(train_df, np.random.default_rng(rng_seed + epoch))  # fresh forecast noise
        return to_tensors(train_df, tf, y_mean, y_std, shift, train_seq, x=tf.transform(noisy))

    val = None
    if val_mask is not None:
        val_df = panel[val_mask & usable(panel, True)]
        val = to_tensors(val_df, tf, y_mean, y_std, shift, seq[val_df.index] if seq is not None else None)
    model, hist = train_cvae(model, make_train, val, fixed_epochs, log)
    fit_core = panel[fit_mask & usable(panel, True)]
    gbm = GBMQuantile().fit(fit_core)
    support = SupportRule().fit(panel[fit_mask & usable(panel, False)])
    info = {"encoder": cfg.encoder, "best_epoch": hist["best_epoch"], "n_train_rows": int(len(train_df)),
            "attendance_sigma_log": att.sigma, "train_end": str(panel.loc[fit_mask, "date"].max().date()),
            "seed": C.SEED, "synthetic_rows": 0 if extra is None else int(len(extra))}
    bundle = ModelBundle(att, tf, model, y_mean, y_std, shift, support, gbm, n_dishes, spread_factor, info)
    return bundle, hist, panel


def calibrate_spread(bundle: ModelBundle, df: pd.DataFrame, seq: np.ndarray | None = None) -> float:
    """Pick the factor k that widens or narrows the P10 to P90 band to reach 80 percent coverage on df.

    The band is P50 + k * (P10 - P50) to P50 + k * (P90 - P50), in log space. Fitted on validation only.
    """
    raw = bundle.predict_cvae(df, seq, calibrated=False)
    lo, mid, hi = (np.log1p(raw[q]) for q in (0.1, 0.5, 0.9))
    y = np.log1p(df["demand_qty"].to_numpy())
    best_k, best_gap = 1.0, np.inf
    for k in np.arange(0.5, 4.01, 0.05):
        cover = np.mean((y >= mid + k * (lo - mid)) & (y <= mid + k * (hi - mid)))
        gap = abs(cover - C.COVERAGE_TARGET)
        if gap < best_gap - 1e-9:
            best_k, best_gap = float(k), gap
    return round(best_k, 2)


def save_history(hist: dict, name: str) -> None:
    """Write learning curves and KL per latent dimension to reports/ as json."""
    out = {k: ([float(x) for x in v] if k != "val_kl_dim" else [[float(x) for x in d] for d in v])
           for k, v in hist.items() if k != "best_epoch"}
    out["best_epoch"] = int(hist["best_epoch"])
    C.REPORTS_DIR.mkdir(exist_ok=True)
    (C.REPORTS_DIR / f"training_history_{name}.json").write_text(json.dumps(out), encoding="utf-8")


def main() -> None:
    """Command line entry point."""
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--encoder", choices=["mlp", "gru"], default="mlp")
    ap.add_argument("--final", action="store_true", help="retrain on train + validation (needs a dev run first)")
    ap.add_argument("--include-test", action="store_true", help="with --final, also train on the test period")
    ap.add_argument("--extra-data", default=None, help="synthetic rows from the GAN (parquet or csv)")
    ap.add_argument("--epochs", type=int, default=None)
    args = ap.parse_args()

    panel, cfg = load_panel(), CVAEConfig(encoder=args.encoder)
    if args.epochs:
        cfg.max_epochs = args.epochs
    seq = load_windows() if args.encoder == "gru" else None
    extra = None
    if args.extra_data:
        from feedforward.plugins.gan_extra_data import load_extra_rows
        extra = load_extra_rows(args.extra_data)
    tag = "" if args.encoder == "mlp" else "_gru"
    if args.final:
        dev = ModelBundle.load(DEV_DIR)
        splits = ["train", "val"] + (["test"] if args.include_test else [])
        bundle, hist, _ = fit_bundle(panel, panel["split"].isin(splits), None, cfg, seq, extra,
                                     fixed_epochs=dev.info["best_epoch"], spread_factor=dev.spread_factor)
        bundle.info["final_splits"] = splits
        bundle.save(FINAL_DIR)
        save_history(hist, "final")
        print(f"final model saved to {FINAL_DIR} (trained on {splits}, {dev.info['best_epoch']} epochs)")
        return
    bundle, hist, panel2 = fit_bundle(panel, panel["split"] == "train", panel["split"] == "val", cfg, seq, extra)
    val_df = panel2[(panel2["split"] == "val") & usable(panel2, True)]
    bundle.spread_factor = calibrate_spread(bundle, val_df, seq[val_df.index] if seq is not None else None)
    bundle.save(C.MODELS_DIR / f"dev{tag}")
    save_history(hist, f"dev{tag}")
    print(f"dev model saved: best epoch {hist['best_epoch']}, spread factor {bundle.spread_factor}")


if __name__ == "__main__":
    main()
