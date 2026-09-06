import os
import math
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from constants import (
    BASELINE_EGT, BASELINE_CHT, MAX_OP
)
from physics.expected import CYL_TRIM_EGT, CYL_TRIM_CHT, calculate_expected, calculate_expected_map, calculate_expected_fuel_flow
from ml.features import to_features


# ── Training data ────────────────────────────────────────────────────────────
RNG = np.random.default_rng(42)

def _nominal_baselines(n: int = 500) -> np.ndarray:
    """
    Produce *n* synthetic nominal-residual vectors.
    Samples throttle across its operational range [40%, 100%].
    """
    rows = []
    for _ in range(n):
        altitude_ft  = RNG.uniform(0, 30_000)
        throttle_pct = RNG.uniform(0.4, 1.0)
        warmup       = RNG.uniform(0.0, 1.0)

        exp = calculate_expected(altitude_ft, throttle_pct * 100.0)
        exp_rpm = exp["expected_rpm"]
        exp_map = calculate_expected_map(altitude_ft, throttle_pct * 100.0)
        exp_ff = calculate_expected_fuel_flow(exp_rpm, altitude_ft, throttle_pct * 100.0)
        
        load_wander = RNG.uniform(-3.0, 3.0)

        rpm     = exp_rpm + load_wander + RNG.uniform(-1, 1)
        map_val = exp_map + RNG.uniform(-0.1, 0.1)
        op      = MAX_OP + RNG.uniform(-0.4, 0.4)
        ff      = exp_ff * (rpm / max(exp_rpm, 1.0)) + RNG.uniform(-0.04, 0.04)

        firing_rate   = max(0.0, rpm / 120.0)

        egt = [
            BASELINE_EGT + firing_rate * 0.16 + CYL_TRIM_EGT[c] * warmup
            + RNG.uniform(-3.0, 3.0) + load_wander * 0.010
            + RNG.uniform(-0.4, 0.4)
            for c in range(4)
        ]
        cht = [
            BASELINE_CHT + firing_rate * 0.05 + CYL_TRIM_CHT[c] + 2.2 * warmup
            + RNG.uniform(-1.4, 1.4) + RNG.uniform(-0.3, 0.3)
            for c in range(4)
        ]
        kurtosis = 2.9 + RNG.uniform(-0.05, 0.05) + RNG.uniform(-0.02, 0.02)

        feats = to_features(rpm, map_val, op, ff, egt, cht, kurtosis,
                              altitude_ft, throttle_pct)
        rows.append(feats)

    return np.array(rows)


# ── Fit or Load the model at import time ────────────────────────────────────
MODEL_PATH = os.path.join(os.path.dirname(__file__), "..", "models", "isolation_forest.pkl")
os.makedirs(os.path.dirname(MODEL_PATH), exist_ok=True)

if os.path.exists(MODEL_PATH):
    # Load cached model and scaler
    cached = joblib.load(MODEL_PATH)
    _scaler = cached["scaler"]
    _model = cached["model"]
else:
    # Train from scratch and cache
    _training_data   = _nominal_baselines(1000)
    _scaler          = StandardScaler().fit(_training_data)
    _scaled_training = _scaler.transform(_training_data)

    _model = IsolationForest(
        n_estimators=200,
        contamination=0.002,
        random_state=42,
    )
    _model.fit(_scaled_training)

    # Save to disk
    joblib.dump({"scaler": _scaler, "model": _model}, MODEL_PATH)


# ── Public API ───────────────────────────────────────────────────────────────
def score_snapshot(telemetry: dict) -> dict:
    throttle_pct = telemetry.get("throttle", 100.0) / 100.0

    feats = to_features(
        telemetry["rpm"],
        telemetry["map"],
        telemetry["op"],
        telemetry["ff"],
        telemetry["egt"],
        telemetry["cht"],
        telemetry["vibration_kurtosis"],
        telemetry.get("altitude_ft", 10_000),
        throttle_pct,
    )
    features = _scaler.transform(np.array([feats]))

    prediction = _model.predict(features)[0]
    raw_score  = float(_model.score_samples(features)[0])

    return {
        "if_label": "NORMAL" if prediction == 1 else "ANOMALY",
        "if_score": round(raw_score, 4),
    }
