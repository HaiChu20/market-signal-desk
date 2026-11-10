"""Versioned, local-only model artifacts and paper-order construction."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import pickle

import numpy as np
import pandas as pd

from msd.methods.common import exit_candidates

ARTIFACT_VERSION = 1
PROTOCOL_VERSION = 2


@dataclass(frozen=True)
class ModelArtifact:
    model: object
    feature_dtypes: dict[str, str]
    calibration: dict
    config_hash: str
    training_range: dict
    protocol_version: int

    def probability(self, features: pd.Series) -> float:
        values = []
        for name, dtype in self.feature_dtypes.items():
            if name not in features:
                raise ValueError(f"missing model feature: {name}")
            value = np.asarray(features[name], dtype=np.dtype(dtype)).item()
            if not np.isfinite(value):
                raise ValueError(f"nonfinite model feature: {name}")
            values.append(value)
        raw = float(self.model.predict_proba(np.asarray([values], dtype=np.float32))[0][1])
        if not np.isfinite(raw) or not 0 <= raw <= 1:
            raise ValueError("invalid model probability")
        x = self.calibration["raw"]
        y = self.calibration["calibrated"]
        return float(np.interp(raw, x, y))


def load_artifact(path: str | Path, *, expected_config_hash: str | None = None) -> ModelArtifact:
    """Load a trusted local pickle after validating the manifest and calibration."""
    root = Path(path)
    manifest = json.loads((root / "manifest.json").read_text())
    if manifest["artifact_version"] != ARTIFACT_VERSION or manifest["protocol_version"] != PROTOCOL_VERSION:
        raise ValueError("unsupported artifact or protocol version")
    config_hash = manifest["config_hash"]
    if len(config_hash) != 64 or any(c not in "0123456789abcdef" for c in config_hash):
        raise ValueError("invalid config hash")
    if expected_config_hash is not None and config_hash != expected_config_hash:
        raise ValueError("model config hash mismatch")
    training = manifest["training_range"]
    if pd.Timestamp(training["start"]) >= pd.Timestamp(training["end"]):
        raise ValueError("invalid training range")
    features = manifest["features"]
    names = [item["name"] for item in features]
    if len(names) != len(set(names)) or not names:
        raise ValueError("duplicate or empty feature list")
    dtypes = {item["name"]: item["dtype"] for item in features}
    for dtype in dtypes.values():
        if np.dtype(dtype) != np.dtype("float32"):
            raise ValueError("model features must use offline float32 dtype")
    calibration = json.loads((root / "calibration.json").read_text())
    x, y = calibration["raw"], calibration["calibrated"]
    if len(x) < 2 or len(x) != len(y) or x[0] != 0 or x[-1] != 1 or y[0] < 0 or y[-1] > 1:
        raise ValueError("invalid calibration grid")
    if any(a >= b for a, b in zip(x, x[1:])) or any(a > b for a, b in zip(y, y[1:])):
        raise ValueError("calibration must be monotone")
    model_bytes = (root / "model.pkl").read_bytes()
    if hashlib.sha256(model_bytes).hexdigest() != manifest["model_sha256"]:
        raise ValueError("model checksum mismatch")
    model = pickle.loads(model_bytes)  # Trusted artifact directory only.
    return ModelArtifact(model, dtypes, calibration, config_hash, training, PROTOCOL_VERSION)


def order_from_event(artifact: ModelArtifact, features: pd.Series, event: dict, levels: pd.DataFrame,
                     *, side: int, candidate_kind: str, min_probability: float = 0.5,
                     risk_budget: float = 1.0, entry_type: str = "market") -> dict | None:
    """Choose an explicitly named offline exit candidate and size to stop risk."""
    if side not in event.get("side_candidates", [event.get("side")]):
        raise ValueError("side is not allowed by event")
    if entry_type not in {"market", "limit"}:
        raise ValueError("unsupported entry type")
    probability = artifact.probability(features)
    if probability < min_probability:
        return None
    oriented = {**event, "side": side}
    atr = float(features["1m_atr14"])
    candidate = next((item for item in exit_candidates(oriented, levels, atr)
                      if item["kind"] == candidate_kind), None)
    if candidate is None:
        raise ValueError("unknown exit candidate")
    price = float(event["price"])
    stop, tp = candidate["sl"], candidate["tp"]
    if stop is None or tp is None or not np.isfinite([price, stop, tp]).all():
        raise ValueError("candidate has no executable SL/TP")
    if side * (price - stop) <= 0 or side * (tp - price) <= 0:
        raise ValueError("candidate SL/TP is on wrong side")
    if not np.isfinite(risk_budget) or risk_budget <= 0:
        raise ValueError("risk budget must be positive")
    return {"decision_ts": event["ts"], "side": side, "entry_type": entry_type,
            "entry_price": price if entry_type == "limit" else None,
            "stop": float(stop), "tp": float(tp), "confidence": probability,
            "size": float(risk_budget / abs(price - stop)),
            "note": f"{event['method']}:{candidate_kind}"}
