"""A trained demand model with everything needed to forecast: save, load and predict quantiles."""

from dataclasses import asdict, dataclass, field

import joblib
import numpy as np
import pandas as pd
import torch

from feedforward import config as C
from feedforward.models.attendance import AttendanceModel
from feedforward.models.baselines import GBMQuantile, SupportRule
from feedforward.models.cvae import CVAE, CVAEConfig, sample_log_quantiles
from feedforward.models.prep import INPUT_COLUMNS, FeatureTransformer

QUANTILES = (0.1, 0.25, 0.5, 0.75, 0.9)


@dataclass
class ModelBundle:
    """Attendance model, feature scaling, CVAE (core dishes), support rule and the GBM baseline."""

    att: AttendanceModel
    tf: FeatureTransformer
    cvae: CVAE
    y_mean: float
    y_std: float
    shift: float
    support: SupportRule
    gbm: GBMQuantile
    n_dishes: int
    spread_factor: float = 1.0          # calibration: widen or narrow the band around P50 (log scale)
    info: dict = field(default_factory=dict)

    def with_attendance(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add expected_attendance from the attendance model unless the caller already supplied it."""
        if "expected_attendance" in df:
            return df
        return df.assign(expected_attendance=self.att.predict(df))

    def offset(self, df: pd.DataFrame) -> np.ndarray:
        """Scaled log expected attendance (plus the typical log rate per attendee), the CVAE's starting point."""
        return (np.log(df["expected_attendance"].to_numpy()) + self.shift - self.y_mean) / self.y_std

    def predict_cvae(self, df: pd.DataFrame, seq: np.ndarray | None = None, n_samples: int = C.N_SAMPLES,
                     calibrated: bool = True) -> dict[float, np.ndarray]:
        """CVAE quantiles in portions for core dish rows. df needs expected_attendance and dish_idx."""
        x = torch.from_numpy(self.tf.transform(df))
        dish = torch.tensor(df["dish_idx"].to_numpy(), dtype=torch.long)
        s = torch.from_numpy(seq) if seq is not None else None
        off = torch.tensor(self.offset(df), dtype=torch.float32).unsqueeze(1)
        logq = sample_log_quantiles(self.cvae, dish, x, s, off, self.y_mean, self.y_std, QUANTILES, n_samples)
        raw = {q: np.clip(np.expm1(v), 0, None) for q, v in logq.items()}
        return self.apply_spread(raw) if calibrated else raw

    def apply_spread(self, raw: dict[float, np.ndarray]) -> dict[float, np.ndarray]:
        """Calibration: move every quantile away from (k > 1) or towards (k < 1) the P50, in log space."""
        mid = np.log1p(raw[0.5])
        return {q: np.clip(np.expm1(mid + self.spread_factor * (np.log1p(v) - mid)), 0, None)
                for q, v in raw.items()}

    def predict(self, df: pd.DataFrame, seq: np.ndarray | None = None, n_samples: int = C.N_SAMPLES,
                calibrated: bool = True) -> dict[float, np.ndarray]:
        """Quantiles in portions for any rows: CVAE for core dishes, the rate rule for support dishes."""
        df = self.with_attendance(df).reset_index(drop=True)
        out = {q: np.zeros(len(df)) for q in QUANTILES}
        core = (df["is_core"] == 1).to_numpy()
        if core.any():
            part = self.predict_cvae(df[core], seq[core] if seq is not None else None, n_samples, calibrated)
            for q in QUANTILES:
                out[q][core] = part[q]
        if (~core).any():
            part = self.support.predict(df[~core])
            for q in QUANTILES:
                out[q][~core] = part[q]
        return out

    def save(self, folder) -> None:
        """Write the bundle to a folder (torch weights plus joblib for the sklearn parts)."""
        folder.mkdir(parents=True, exist_ok=True)
        torch.save({"state": self.cvae.state_dict(), "cfg": asdict(self.cvae.cfg), "n_dishes": self.n_dishes,
                    "n_num": len(INPUT_COLUMNS)},
                   folder / "cvae.pt")
        joblib.dump({"att": self.att, "tf": self.tf, "support": self.support, "gbm": self.gbm,
                     "y_mean": self.y_mean, "y_std": self.y_std, "shift": self.shift, "spread_factor": self.spread_factor,
                     "info": self.info}, folder / "parts.joblib")

    @classmethod
    def load(cls, folder) -> "ModelBundle":
        """Read a bundle written by save()."""
        ck = torch.load(folder / "cvae.pt", weights_only=False)
        model = CVAE(ck["n_dishes"], ck["n_num"], CVAEConfig(**ck["cfg"]))
        model.load_state_dict(ck["state"])
        model.eval()
        p = joblib.load(folder / "parts.joblib")
        return cls(att=p["att"], tf=p["tf"], cvae=model, y_mean=p["y_mean"], y_std=p["y_std"], shift=p["shift"],
                   support=p["support"], gbm=p["gbm"], n_dishes=ck["n_dishes"],
                   spread_factor=p["spread_factor"], info=p["info"])
