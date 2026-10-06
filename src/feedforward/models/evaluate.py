"""Evaluate the models on validation, test and rolling origin folds, and simulate the cooking decision.

python -m feedforward.models.evaluate        (needs: python -m feedforward.models.train)
Writes reports/metrics.json and PNG plots. Everything uses held out rows only.
"""

import json
from dataclasses import replace

import numpy as np
import pandas as pd

from feedforward import config as C
from feedforward.data.splits import rolling_origin_folds
from feedforward.data.timeseries import load_clean_history
from feedforward.models import plots
from feedforward.models.attendance import add_expected_attendance, slot_table
from feedforward.models.baselines import last_week, mean_last_three, usual_plan
from feedforward.models.bundle import ModelBundle
from feedforward.models.cvae import CVAEConfig
from feedforward.models.metrics import calibration_points, round_portions, score, simulate_decision
from feedforward.models.summary import summary_markdown
from feedforward.models.train import DEV_DIR, calibrate_spread, fit_bundle, load_panel, load_windows, usable

GBM_Q = (0.1, 0.5, 0.9)


def model_predictions(bundle: ModelBundle, df: pd.DataFrame, core: bool, seq=None) -> dict:
    """Forecasts of every model for the rows of df (all core, or all support, dishes)."""
    preds = {"last_week": last_week(df), "mean_last_3": mean_last_three(df), "usual_plan": df["usual_plan"].to_numpy()}
    if core:
        raw = bundle.predict_cvae(df, seq, calibrated=False)
        preds["gbm_quantile"] = bundle.gbm.predict(df)
        preds["cvae_raw"] = raw
        preds["cvae_calibrated"] = bundle.apply_spread(raw)
    else:
        preds["rate_rule"] = bundle.support.predict(df)
    return preds


def evaluate_rows(bundle: ModelBundle, df: pd.DataFrame, seq=None) -> tuple[dict, dict]:
    """Metrics by scope (core regular, core limited stock, support) and the raw predictions of core rows."""
    result, core_preds = {}, {}
    scopes = {"core_regular": (True, df["special_limited"] == 0), "core_limited": (True, df["special_limited"] == 1),
              "support": (False, df["is_core"] == 0)}
    for name, (core, mask) in scopes.items():
        part = df[mask & (df["is_core"] == int(core))]
        if part.empty:
            continue
        preds = model_predictions(bundle, part, core, seq[part.index] if seq is not None else None)
        y = part["demand_qty"].to_numpy()
        result[name] = {"rows": len(part), **{m: score(y, p) for m, p in preds.items()}}
        if core:
            core_preds[name] = (part, preds)
    return result, core_preds


def prepare_panel() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Panel with the usual plan added, and the clean history."""
    history = load_clean_history()
    panel = load_panel().reset_index(drop=True)
    panel["usual_plan"] = usual_plan(history, panel).to_numpy()
    return panel, history


def regime_table(frames: list[pd.DataFrame]) -> dict:
    """MAE of every point forecast by regime, over the pooled held out rows."""
    all_rows = pd.concat(frames, ignore_index=True)
    cols = [c for c in all_rows.columns if c.startswith("p50_")]
    table = {}
    for reg, g in all_rows.groupby("regime"):
        table[reg] = {"rows": len(g), **{c[4:]: float(np.mean(np.abs(g[c] - g["demand_qty"]))) for c in cols}}
    return table


def row_frame(part: pd.DataFrame, preds: dict) -> pd.DataFrame:
    """Held out rows with every model's P50, for the regime table and plots."""
    out = part[["date", "meal_slot", "dish_id", "regime", "demand_qty", "special_limited"]].copy()
    for name, p in preds.items():
        out[f"p50_{name}"] = p[0.5] if isinstance(p, dict) else p
    return out


def rolling_origin(panel: pd.DataFrame, cfg: CVAEConfig) -> tuple[list, list]:
    """Retrain on everything before each 28 day block (last 28 days of it used to stop early) and test on the block."""
    results, frames = [], []
    for fold in rolling_origin_folds():
        val_start = fold["train_end"] - pd.Timedelta(days=C.FOLD_DAYS - 1)
        fit = panel["date"] < val_start
        val = (panel["date"] >= val_start) & (panel["date"] <= fold["train_end"])
        bundle, hist, p2 = fit_bundle(panel, fit, val, cfg, log=False)
        vdf = p2[val & usable(p2, True)]
        bundle.spread_factor = calibrate_spread(bundle, vdf)
        test = p2[(p2["date"] >= fold["test_start"]) & (p2["date"] <= fold["test_end"])]
        test = test[test["n_lags"] > 0]
        res, core_preds = evaluate_rows(bundle, test)
        results.append({"fold": fold["fold"], "test": f"{fold['test_start'].date()} to {fold['test_end'].date()}",
                        "best_epoch": hist["best_epoch"], "spread_factor": bundle.spread_factor, **res})
        part, preds = core_preds["core_regular"]
        frames.append(row_frame(part, preds))
        print(f"fold {fold['fold']} done", flush=True)
    return results, frames


def attendance_report(att_panel: pd.DataFrame) -> dict:
    """Attendance forecaster accuracy (MAPE) against the naive same weekday last week."""
    s = slot_table(att_panel[att_panel["n_lags"] > 0])
    out = {}
    for sp in ("train", "val", "test"):
        d = s[s["split"] == sp]
        out[sp] = {"model_mape_pct": float(100 * np.mean(np.abs(d["expected_attendance"] - d["attendance"]) / d["attendance"])),
                   "naive_last_week_mape_pct": float(100 * np.mean(np.abs(d["slot_att_lag_7"] - d["attendance"]) / d["attendance"])),
                   "note": "train rows are out of fold predictions"}
    return out


def decision_simulation(part: pd.DataFrame, preds: dict, history: pd.DataFrame) -> dict:
    """Cook the P75 recommendation versus the usual plan versus what the manager actually prepared (test period)."""
    rec = round_portions(preds["cvae_calibrated"][C.RECOMMEND_QUANTILE])
    actual = history.set_index(["date", "meal_slot", "dish_id"])
    key = pd.MultiIndex.from_frame(part[["date", "meal_slot", "dish_id"]])
    prepared = actual.loc[key, "prepared_qty"].to_numpy()
    topup = actual.loc[key, "topup_qty"].to_numpy()
    by_quantile = {f"cvae_p{int(q * 100)}_recommendation": simulate_decision(part, round_portions(preds["cvae_calibrated"][q]))
                   for q in (0.5, 0.9)}
    return {"note": "Top ups are ignored for the first three policies, so shortage is the shortage BEFORE any top up. "
                    "The last row counts the top ups the kitchen really did, so it is not a like for like comparison.",
            "cvae_p75_recommendation": simulate_decision(part, rec), **by_quantile,
            "usual_plan": simulate_decision(part, preds["usual_plan"]),
            "manager_prepared_only": simulate_decision(part, prepared),
            "manager_prepared_plus_actual_topup": simulate_decision(part, prepared + topup)}


def latent_ablation(panel: pd.DataFrame, dev: ModelBundle, val_mask, df_val, cfg: CVAEConfig) -> dict:
    """Posterior collapse check: free bits 0 versus the chosen setting, on validation."""
    out = {}
    for fb in sorted({0.0, cfg.free_bits}):
        if fb == cfg.free_bits:
            bundle, kl = dev, None
        else:
            bundle, hist, _ = fit_bundle(panel, panel["split"] == "train", val_mask, replace(cfg, free_bits=fb), log=False)
            bundle.spread_factor = calibrate_spread(bundle, df_val)
            kl = hist["val_kl_dim"][hist["best_epoch"] - 1]
        raw = bundle.predict_cvae(df_val, calibrated=False)
        y = df_val["demand_qty"].to_numpy()
        out[f"free_bits_{fb}"] = {"mae_p50": float(np.mean(np.abs(raw[0.5] - y))), "raw_coverage": score(y, raw)["coverage_10_90"],
                                  "kl_per_dim": None if kl is None else [float(k) for k in kl]}
    return out


def gru_comparison(p2: pd.DataFrame, seq: np.ndarray) -> dict | str:
    """Optional experiment: GRU history encoder versus the default MLP, regular core dishes (needs train --encoder gru)."""
    folder = C.MODELS_DIR / "dev_gru"
    if not folder.exists():
        return "not run (python -m feedforward.models.train --encoder gru)"
    gru = ModelBundle.load(folder)
    out = {}
    for split in ("val", "test"):
        df = p2[(p2["split"] == split) & usable(p2, True) & (p2["special_limited"] == 0)]
        raw = gru.predict_cvae(df, seq[df.index], calibrated=False)
        out[split] = {"cvae_gru_raw": score(df["demand_qty"].to_numpy(), raw),
                      "cvae_gru_calibrated": score(df["demand_qty"].to_numpy(), gru.apply_spread(raw))}
    return out


def main() -> None:
    """Run every evaluation and write reports/metrics.json plus plots."""
    panel, history = prepare_panel()
    cfg = CVAEConfig()
    dev = ModelBundle.load(DEV_DIR)
    train_mask = panel["split"] == "train"
    p2, _ = add_expected_attendance(panel, train_mask)
    metrics = {"data_note": "history is SIMULATED on a real menu, calendar and weather", "attendance": attendance_report(p2),
               "dev_model": dev.info | {"spread_factor": dev.spread_factor}}
    frames_test, test_core = [], None
    for split in ("val", "test"):
        df = p2[(p2["split"] == split) & (p2["n_lags"] > 0)]
        metrics[split], core_preds = evaluate_rows(dev, df)
        part, preds = core_preds["core_regular"]
        if split == "test":
            test_core = (part, preds)
            frames_test.append(row_frame(part, preds))
        if split == "val":
            val_core = (part, preds)
    metrics["calibration_points"] = {
        s: {m: calibration_points(part["demand_qty"].to_numpy(), preds[m]) for m in ("cvae_raw", "cvae_calibrated", "gbm_quantile")}
        for s, (part, preds) in (("val", val_core), ("test", test_core))}
    metrics["decision_simulation_test"] = decision_simulation(*test_core, history)
    val_df = p2[(p2["split"] == "val") & usable(p2, True)]
    metrics["latent_ablation_val"] = latent_ablation(panel, dev, panel["split"] == "val", val_df, cfg)
    metrics["gru_experiment"] = gru_comparison(p2, load_windows())
    folds, fold_frames = rolling_origin(panel, cfg)
    metrics["rolling_origin"] = folds
    metrics["by_regime_core_regular"] = regime_table(frames_test + fold_frames)
    (C.REPORTS_DIR / "metrics.json").write_text(json.dumps(metrics, indent=2, default=float), encoding="utf-8")
    (C.REPORTS_DIR / "metrics_summary.md").write_text(summary_markdown(metrics), encoding="utf-8")
    plots.make_all(test_core, metrics, history)
    print("wrote reports/metrics.json, metrics_summary.md and plots")


if __name__ == "__main__":
    main()
