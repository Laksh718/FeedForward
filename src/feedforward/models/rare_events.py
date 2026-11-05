"""Rare event plans: what a festival, holiday, exam week or heavy rain does to a meal, from two independent models.

1. The forecast with the event applied: the conditional VAE, with the day's calendar or weather changed the same way
   a real calendar entry would change it (the what if machinery).
2. Generated demand: the rare event GAN (feedforward.models.gan, trained by feedforward.models.train_gan) draws a few
   hundred possible demands for each main dish under the event. Its spread shows how differently such days can turn
   out, and is compared with the quantity the forecast recommends.

The GAN covers main dishes only (it was trained on them). If it has not been trained, the forecast part still works
and `generated.available` is False with a note that says how to train it.
"""

from functools import lru_cache

import numpy as np
import pandas as pd

from feedforward import config as C
from feedforward.data.features import build_features, menu_rows_for
from feedforward.models.forecast_service import ForecastService, Overrides, apply_date_overrides

EVENTS = {
    "festival": {"label": "Festival", "overrides": {"festival": True}, "gan": "festival",
                 "about": "A major festival: many students go home, and those who stay often eat a special meal."},
    "holiday": {"label": "Holiday or campus event", "overrides": {"special_day": True}, "gan": "holiday",
                "about": "A declared holiday or campus event: no classes, a late breakfast and a lighter day."},
    "exam_week": {"label": "Exam week", "overrides": {"exam_week": True}, "gan": "exam_week",
                  "about": "University exams: students stay on campus and meal times shift around the papers."},
    "rain": {"label": "Heavy rain", "overrides": {"weather_type": "Heavy Rain"}, "gan": "rain",
             "about": "A heavy rain day: fewer people walk to the mess, and hot dishes sell better."},
}
DRAWS = 300
MAX_ABOVE_DISH_MAX = 1.3   # same limit as the checks on generated training rows (plugins.gan_extra_data)
HIST_BINS = 14


def event_overrides(event: str, attendance_change_pct: float | None = None) -> Overrides:
    """The what if settings that stand for an event (plus an optional attendance change)."""
    if event not in EVENTS:
        raise ValueError(f"Unknown event '{event}'. Choose one of {sorted(EVENTS)}.")
    return Overrides(**EVENTS[event]["overrides"], attendance_change_pct=attendance_change_pct)


@lru_cache(maxsize=1)
def _generator():
    """The trained generator and scaler, or None when the GAN has not been trained on this machine."""
    from feedforward.data.gan_data import GAN_DIR
    if not (GAN_DIR / "generator.pt").exists() or not (GAN_DIR / "scaler.joblib").exists():
        return None
    from feedforward.plugins.gan_extra_data import load_generator
    return load_generator(GAN_DIR)


def gan_available() -> bool:
    """True when the trained GAN is on disk."""
    return _generator() is not None


def _histogram(values: np.ndarray) -> list[dict]:
    lo, hi = float(np.percentile(values, 1)), float(np.percentile(values, 99))
    if hi <= lo:
        hi = lo + 1
    counts, edges = np.histogram(np.clip(values, lo, hi), bins=HIST_BINS, range=(lo, hi))
    return [{"lo": int(round(edges[i])), "hi": int(round(edges[i + 1])), "count": int(c)} for i, c in enumerate(counts)]


def generate(svc: ForecastService, day, slot: str, event: str, attendance_change_pct: float | None = None,
             draws: int = DRAWS, seed: int = C.SEED) -> dict:
    """Generated demand for the main dishes of one meal under an event: quantiles per dish and for the total."""
    loaded = _generator()
    if loaded is None:
        return {"available": False, "draws": 0, "dishes": {}, "total": None,
                "note": "The rare event GAN is not trained on this server. Run: python -m feedforward.data.gan_data, "
                        "then python -m feedforward.models.train_gan"}
    import torch

    from feedforward.data.gan_data import with_gan_columns
    from feedforward.models.gan import sample

    gen, scaler = loaded
    day = pd.Timestamp(day).normalize()
    targets = menu_rows_for(pd.DatetimeIndex([day]), svc.menu)
    targets = targets[targets["meal_slot"] == slot].reset_index(drop=True)
    ov = event_overrides(event, attendance_change_pct)
    feats = apply_date_overrides(build_features(targets, svc.history, svc.dishes), ov) if len(targets) else targets
    if len(feats):
        feats["expected_attendance"] = svc.bundle.att.predict(feats) * (1 + (attendance_change_pct or 0) / 100)
        feats = feats[feats["is_core"] == 1].reset_index(drop=True)
    if not len(feats):
        return {"available": True, "draws": 0, "dishes": {}, "total": None, "note": "No main dishes on the menu for this meal."}
    rows = with_gan_columns(feats, svc.dishes).assign(event_type=EVENTS[event]["gan"])
    cond = torch.from_numpy(scaler.conditions(rows))
    scaled = sample(gen, cond.repeat(draws, 1), seed).numpy()
    demand = scaler.to_demand(scaled).reshape(draws, len(rows))
    hist = svc.history
    dish_max = (hist["consumed_qty"] + hist["unmet_qty"]).groupby(hist["dish_id"]).max()
    cap = rows["dish_id"].map(dish_max).fillna(np.inf).to_numpy() * MAX_ABOVE_DISH_MAX
    demand = np.minimum(demand, cap)            # the same plausibility limit the training rows had to pass
    quant = {q: np.percentile(demand, q, axis=0) for q in (10, 25, 50, 75, 90)}
    dishes = {d: {f"p{q}": int(round(quant[q][i])) for q in quant} | {"mean": int(round(demand[:, i].mean()))}
              for i, d in enumerate(rows["dish_id"])}
    total = demand.sum(axis=1)
    return {"available": True, "draws": draws, "dishes": dishes,
            "total": {f"p{q}": int(round(np.percentile(total, q))) for q in (10, 25, 50, 75, 90)} | {"histogram": _histogram(total)},
            "note": "Generated by the rare event GAN: each draw is one possible day under this event. Main dishes only."}


def verdict(cook: int, gen: dict | None) -> str:
    """How a quantity to cook compares with the generated demand: covered, may run short or may be left over."""
    if not gen:
        return "no_generated"
    if cook < gen["p50"]:
        return "may_run_short"
    if cook > gen["p90"]:
        return "may_be_left_over"
    return "covered"
