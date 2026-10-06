"""Forecast metrics: point error, pinball loss, interval coverage, and the cooking decision simulation."""

import numpy as np
import pandas as pd


def mae(y: np.ndarray, p: np.ndarray) -> float:
    """Mean absolute error in portions."""
    return float(np.mean(np.abs(y - p)))


def rmse(y: np.ndarray, p: np.ndarray) -> float:
    """Root mean squared error in portions."""
    return float(np.sqrt(np.mean((y - p) ** 2)))


def pinball(y: np.ndarray, p: np.ndarray, q: float) -> float:
    """Pinball (quantile) loss: penalises under-forecasting by q and over-forecasting by 1 - q."""
    d = y - p
    return float(np.mean(np.maximum(q * d, (q - 1) * d)))


def coverage(y: np.ndarray, lo: np.ndarray, hi: np.ndarray) -> float:
    """Share of outcomes inside the band (the P10 to P90 band should hold about 80 percent)."""
    return float(np.mean((y >= lo) & (y <= hi)))


def round_portions(x: np.ndarray | float) -> np.ndarray | float:
    """Round a quantity to the nearest 5 portions below 100 and the nearest 10 from 100 up."""
    x = np.asarray(x, dtype=float)
    return np.where(x < 100, np.round(x / 5) * 5, np.round(x / 10) * 10)


def score(y: np.ndarray, preds: dict) -> dict:
    """All metrics for one model. preds is either an array (point forecast) or {quantile: array}."""
    if not isinstance(preds, dict):
        return {"mae": mae(y, preds), "rmse": rmse(y, preds)}
    out = {"mae": mae(y, preds[0.5]), "rmse": rmse(y, preds[0.5])}
    for q in (0.1, 0.5, 0.9):
        out[f"pinball_{q}"] = pinball(y, preds[q], q)
    out["coverage_10_90"] = coverage(y, preds[0.1], preds[0.9])
    out["width_10_90"] = float(np.mean(preds[0.9] - preds[0.1]))
    return out


def calibration_points(y: np.ndarray, preds: dict) -> dict:
    """For each forecast quantile q, the share of outcomes at or below it (ideal: equal to q)."""
    return {q: float(np.mean(y <= p)) for q, p in preds.items()}


def simulate_decision(df: pd.DataFrame, cook: np.ndarray) -> dict:
    """What would have happened if `cook` portions had been prepared (top ups ignored).

    leftover = cooked but not eaten; shortage = demand that could not be served.
    """
    demand = df["demand_qty"].to_numpy()
    left, short = np.maximum(cook - demand, 0), np.maximum(demand - cook, 0)
    return {"cooked": float(cook.sum()), "leftover": float(left.sum()), "shortage": float(short.sum()),
            "leftover_pct_of_cooked": float(100 * left.sum() / max(cook.sum(), 1)),
            "shortage_pct_of_demand": float(100 * short.sum() / max(demand.sum(), 1)),
            "rows_short": int((short > 0).sum()), "rows": int(len(df))}
