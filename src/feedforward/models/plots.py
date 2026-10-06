"""Evaluation plots saved to reports/: fan chart, calibration, learning curves, error by regime."""

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from feedforward import config as C  # noqa: E402

INK, MUTED, GRID = "#17233B", "#5B6478", "#E3E7F0"
BLUE, BAND, ORANGE, GREY = "#2C55B8", "#BFD0F0", "#E5702A", "#9AA3B5"
plt.rcParams.update({"font.size": 10, "axes.edgecolor": GRID, "axes.labelcolor": MUTED, "text.color": INK,
                     "xtick.color": MUTED, "ytick.color": MUTED, "axes.spines.top": False,
                     "axes.spines.right": False, "axes.grid": True, "grid.color": GRID, "grid.linewidth": 0.8,
                     "figure.dpi": 130, "savefig.bbox": "tight"})


def _save(fig, name: str) -> None:
    """Write a figure to reports/ and close it."""
    fig.savefig(C.REPORTS_DIR / name)
    plt.close(fig)


def fan_chart(test_core: tuple, name_of: dict) -> None:
    """Forecast range against actual demand for the four biggest regular dishes at lunch, test period."""
    part, preds = test_core
    cal = preds["cvae_calibrated"]
    df = part.assign(p10=cal[0.1], p50=cal[0.5], p90=cal[0.9], usual=preds["usual_plan"])
    df = df[df["meal_slot"] == "lunch"]
    top = df.groupby("dish_id")["demand_qty"].mean().nlargest(4).index
    fig, axes = plt.subplots(2, 2, figsize=(11, 6.4), sharex=True)
    for ax, dish in zip(axes.ravel(), top, strict=False):
        d = df[df["dish_id"] == dish].sort_values("date")
        ax.fill_between(d["date"], d["p10"], d["p90"], color=BAND, label="Likely range (P10 to P90)", lw=0)
        ax.plot(d["date"], d["p50"], color=BLUE, lw=2, label="Most likely (P50)")
        ax.plot(d["date"], d["usual"], color=ORANGE, lw=1.4, ls="--", label="Usual plan")
        ax.plot(d["date"], d["demand_qty"], color=INK, lw=0, marker="o", ms=3.5, label="Actual demand")
        ax.set_title(name_of.get(dish, dish), loc="left", fontsize=10.5, color=INK)
        ax.tick_params(axis="x", rotation=30)
    handles, labels = axes[0, 0].get_legend_handles_labels()
    fig.legend(handles, labels, frameon=False, fontsize=9, loc="lower center", ncol=4, bbox_to_anchor=(0.5, -0.04))
    fig.suptitle("Lunch demand, test period: forecast range and actuals (calibrated CVAE)", x=0.01, ha="left")
    _save(fig, "fan_chart.png")


def calibration_plot(points: dict) -> None:
    """Share of outcomes below each forecast quantile. A perfect model lies on the diagonal."""
    fig, axes = plt.subplots(1, 2, figsize=(9, 4.2), sharey=True)
    styles = {"cvae_raw": (GREY, "CVAE before calibration"), "cvae_calibrated": (BLUE, "CVAE calibrated"),
              "gbm_quantile": (ORANGE, "Gradient boosting")}
    for ax, split in zip(axes, ("val", "test"), strict=True):
        ax.plot([0, 1], [0, 1], color=MUTED, lw=1, ls=":")
        for model, (color, label) in styles.items():
            pts = sorted((float(q), v) for q, v in points[split][model].items())
            ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", ms=5, color=color, lw=2, label=label)
        ax.set_title("Validation" if split == "val" else "Test", loc="left")
        ax.set_xlabel("Forecast quantile")
    axes[0].set_ylabel("Share of outcomes at or below it")
    axes[1].legend(frameon=False, fontsize=8, loc="upper left")
    _save(fig, "calibration.png")


def learning_curves(history: dict) -> None:
    """Training and validation loss, and KL per epoch (posterior collapse check) with the beta schedule."""
    fig, (a, b) = plt.subplots(1, 2, figsize=(10, 4))
    ep = np.arange(1, len(history["train_loss"]) + 1)
    a.plot(ep, history["train_loss"], color=GREY, lw=2, label="Training")
    a.plot(ep, history["val_loss"], color=BLUE, lw=2, label="Validation (beta = 1)")
    a.axvline(history["best_epoch"], color=ORANGE, ls="--", lw=1.2)
    a.text(history["best_epoch"], a.get_ylim()[1], " early stop", color=ORANGE, va="top", fontsize=8)
    a.set_xlabel("Epoch")
    a.set_ylabel("Loss (reconstruction + KL)")
    a.legend(frameon=False, fontsize=8)
    b.plot(ep, history["train_kl"], color=BLUE, lw=2, label="KL (training)")
    b.plot(ep, np.array(history["beta"]), color=GREY, lw=1.5, ls=":", label="beta (annealing)")
    b.set_xlabel("Epoch")
    b.set_ylabel("Nats")
    b.legend(frameon=False, fontsize=8)
    fig.suptitle("Learning curves of the conditional VAE", x=0.01, ha="left")
    _save(fig, "learning_curves.png")


def regime_errors(table: dict) -> None:
    """Mean absolute error in portions by regime for each model."""
    models = [("last_week", "Same weekday last week", GREY), ("usual_plan", "Usual plan", ORANGE),
              ("gbm_quantile", "Gradient boosting", "#7A8FC4"), ("cvae_calibrated", "CVAE", BLUE)]
    regimes = list(table)
    fig, ax = plt.subplots(figsize=(9, 4.2))
    width = 0.8 / len(models)
    for i, (key, label, color) in enumerate(models):
        vals = [table[r][key] for r in regimes]
        ax.bar(np.arange(len(regimes)) + i * width, vals, width * 0.9, color=color, label=label)
    ax.set_xticks(np.arange(len(regimes)) + width * 1.5, [f"{r}\n({table[r]['rows']} rows)" for r in regimes])
    ax.set_ylabel("Mean absolute error (portions)")
    ax.legend(frameon=False, fontsize=8)
    ax.grid(axis="x", visible=False)
    _save(fig, "error_by_regime.png")


def make_all(test_core: tuple, metrics: dict, history: pd.DataFrame) -> None:
    """Write every evaluation plot."""
    dishes = pd.read_parquet(C.PROCESSED_DIR / "dishes.parquet")
    fan_chart(test_core, dict(zip(dishes["dish_id"], dishes["dish_name"], strict=True)))
    calibration_plot(metrics["calibration_points"])
    learning_curves(json.loads((C.REPORTS_DIR / "training_history_dev.json").read_text(encoding="utf-8")))
    regime_errors(metrics["by_regime_core_regular"])
