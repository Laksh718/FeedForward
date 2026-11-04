"""Does the GAN help the CVAE? Same seed, same settings, with and without the synthetic rows.

python reports/gan_ablation.py            (needs artifacts/gan/extra_rows.csv, see the README GAN section)

Every model is trained in memory only (nothing is written to artifacts/models). Test rows are real, core dishes of the
test period. "Rare days" are test rows whose event type is festival, holiday, exam week or rain.
The weights of the GAN rows are both tried (no tuning on the test period, both results are reported).
Also: train on synthetic rows, test on real rare rows (TSTR), next to the same model trained on real rare rows.
"""

import sys
import time
import warnings
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT)]
warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
import torch  # noqa: E402
from sklearn.ensemble import HistGradientBoostingRegressor  # noqa: E402

from feedforward import config as C  # noqa: E402
from feedforward.data.gan_data import GAN_DIR, event_type  # noqa: E402
from feedforward.models.cvae import CVAEConfig  # noqa: E402
from feedforward.models.metrics import mae, rmse, score  # noqa: E402
from feedforward.models.prep import FeatureTransformer  # noqa: E402
from feedforward.models.train import calibrate_spread, fit_bundle, load_panel, usable  # noqa: E402
from feedforward.plugins.gan_extra_data import load_extra_rows  # noqa: E402

SEEDS = (42, 43, 44)
WEIGHTS = (0.3, 0.1)        # the default weight, and a smaller one
METRICS = ("mae", "rmse", "pinball_0.1", "pinball_0.5", "pinball_0.9", "coverage_10_90", "width_10_90")


def run(seed: int, extra: pd.DataFrame | None, weight: float) -> dict:
    """Train one CVAE (seed set before the model is built) and score it on the test period."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    panel = load_panel()
    cfg = CVAEConfig()
    ex = None if extra is None else extra.assign(sample_weight=weight)
    bundle, hist, p2 = fit_bundle(panel, panel["split"] == "train", panel["split"] == "val", cfg, extra=ex, log=False)
    val = p2[(p2["split"] == "val") & usable(p2, True)]
    bundle.spread_factor = calibrate_spread(bundle, val)
    test = p2[(p2["split"] == "test") & usable(p2, True)]
    rare = (event_type(test) != "normal").to_numpy()
    preds = bundle.predict_cvae(test, calibrated=True)
    raw = bundle.predict_cvae(test, calibrated=False)
    out = {"epochs": len(hist["train_loss"]), "best_epoch": hist["best_epoch"], "spread_factor": bundle.spread_factor}
    for name, mask in (("all", np.ones(len(test), bool)), ("rare", rare)):
        y = test["demand_qty"].to_numpy()[mask]
        out[name] = score(y, {q: v[mask] for q, v in preds.items()}) | {
            "rows": int(mask.sum()), "raw_coverage": score(y, {q: v[mask] for q, v in raw.items()})["coverage_10_90"]}
    return out


def tstr(extra: pd.DataFrame) -> dict:
    """A small gradient boosting model trained only on synthetic rows, scored on real rare test rows; and on real rare train rows."""
    from feedforward.models.attendance import add_expected_attendance
    panel = load_panel().reset_index(drop=True)
    panel, _ = add_expected_attendance(panel, panel["split"] == "train")
    core = panel[usable(panel, True)]
    rare_flag = event_type(core) != "normal"
    real_train, test = core[(core["split"] == "train") & rare_flag], core[(core["split"] == "test") & rare_flag]
    out = {"real_test_rows": len(test), "synthetic_rows": len(extra), "real_train_rare_rows": len(real_train)}
    for name, data in (("trained_on_synthetic_only", extra), ("trained_on_real_rare_only", real_train)):
        tf = FeatureTransformer().fit(data)
        model = HistGradientBoostingRegressor(max_depth=5, learning_rate=0.05, max_iter=300, random_state=C.SEED)
        model.fit(tf.transform(data), np.log1p(data["demand_qty"].to_numpy()))
        pred = np.clip(np.expm1(model.predict(tf.transform(test))), 0, None)
        out[name] = {"mae": mae(test["demand_qty"].to_numpy(), pred), "rmse": rmse(test["demand_qty"].to_numpy(), pred)}
    return out


def table(rows: dict[str, list[dict]], scope: str) -> list[str]:
    """Markdown table: mean over seeds of every metric for each setting."""
    head = "| Setting | Rows | MAE | RMSE | Pinball 0.1 / 0.5 / 0.9 | Coverage P10-P90 (raw) | Mean width |"
    lines = [head, "|---|---|---|---|---|---|---|"]
    for name, runs in rows.items():
        m = {k: float(np.mean([r[scope][k] for r in runs])) for k in (*METRICS, "raw_coverage")}
        lines.append(f"| {name} | {runs[0][scope]['rows']} | {m['mae']:.1f} | {m['rmse']:.1f} | {m['pinball_0.1']:.1f} / "
                     f"{m['pinball_0.5']:.1f} / {m['pinball_0.9']:.1f} | {100 * m['coverage_10_90']:.0f}% ({100 * m['raw_coverage']:.0f}%) | "
                     f"{m['width_10_90']:.0f} |")
    return lines


def main() -> None:
    """Run all trainings, write reports/gan_ablation.md."""
    extra = load_extra_rows(GAN_DIR / "extra_rows.csv")
    results: dict[str, list[dict]] = {"without GAN rows": [], **{f"with GAN rows, weight {w}": [] for w in WEIGHTS}}
    t0 = time.time()
    for seed in SEEDS:
        results["without GAN rows"].append(run(seed, None, 1.0))
        for w in WEIGHTS:
            results[f"with GAN rows, weight {w}"].append(run(seed, extra, w))
        print(f"seed {seed} done ({time.time() - t0:.0f} s)", flush=True)
    t = tstr(extra)
    base = results["without GAN rows"]
    lines = ["# Does the GAN help? Ablation on the test period", "",
             "Generated by `python reports/gan_ablation.py`. History is SIMULATED, so this measures the models on the simulation.",
             f"- Test period {C.TEST_START} to {C.TEST_END}, real core dish rows only. Rare days = festival, holiday, exam week or heavy rain.",
             f"- Same settings and same seed in every pair (seeds {list(SEEDS)}); numbers below are the mean of the {len(SEEDS)} seeds. "
             "Full epochs (early stopping, patience 15), so no epoch reduction was needed. Models are trained in memory only.",
             f"- GAN rows: {len(extra)} rows from `artifacts/gan/extra_rows.csv`, tried at weight 0.3 (default) and 0.1; both are reported, "
             "nothing was tuned on the test period. Coverage shows the calibrated band, raw (uncalibrated) in brackets.", "",
             "## All test days", "", *table(results, "all"), "", "## Rare test days only", "", *table(results, "rare"), "",
             "## Rare day MAE of P50 for every seed", "", "| Setting | " + " | ".join(f"seed {s}" for s in SEEDS) + " |",
             "|---|" + "---|" * len(SEEDS)]
    for name, runs in results.items():
        lines.append(f"| {name} | " + " | ".join(f"{r['rare']['mae']:.1f}" for r in runs) + " |")
    lines += ["", "## Train on synthetic, test on real (rare test days)", "",
              f"A gradient boosting model on the same inputs. Real rare test rows: {t['real_test_rows']}.", "",
              "| Training data | Rows | MAE | RMSE |", "|---|---|---|---|",
              f"| synthetic rows only | {t['synthetic_rows']} | {t['trained_on_synthetic_only']['mae']:.1f} | {t['trained_on_synthetic_only']['rmse']:.1f} |",
              f"| real rare train rows only | {t['real_train_rare_rows']} | {t['trained_on_real_rare_only']['mae']:.1f} | {t['trained_on_real_rare_only']['rmse']:.1f} |",
              "", "## Verdict", ""]
    for w in WEIGHTS:
        runs = results[f"with GAN rows, weight {w}"]
        for scope in ("rare", "all"):
            diff = [r[scope]["mae"] - b[scope]["mae"] for r, b in zip(runs, base, strict=True)]
            word = "lower (better)" if all(d < 0 for d in diff) else "higher (worse)" if all(d > 0 for d in diff) else "mixed"
            lines.append(f"- Weight {w}, {scope} days: MAE of P50 changes by {', '.join(f'{d:+.1f}' for d in diff)} per seed "
                         f"(mean {np.mean(diff):+.1f}): {word}.")
    lines += ["", "A change is only a real gain if it is lower for every seed and clearly larger than the spread between seeds. "
              "Otherwise the GAN rows did not help."]
    (ROOT / "reports" / "gan_ablation.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("wrote reports/gan_ablation.md")


if __name__ == "__main__":
    main()
