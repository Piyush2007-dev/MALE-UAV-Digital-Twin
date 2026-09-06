"""
Isolation Forest anomaly pre-filter for the MALE-UAV Digital Twin.

Trains once at import time on synthetic *nominal* telemetry residuals
(deviations from the ISA-predicted baseline), then exposes a single
function ``score_snapshot(telemetry)`` that returns a label + score
for each live snapshot.

This module runs **alongside** the existing threshold-based anomaly
detection — it does not replace or modify it.

The ISA baselines are throttle-aware and apply turbocharger compensation,
eliminating false anomalies at partial throttle. The training data
samples throttle across its full operational range.
"""

import os
import math
import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from constants import (
    T0, L, CRITICAL_ALTITUDE_FT, FT_TO_M,
    BASELINE_EGT, BASELINE_CHT, MAX_OP, IDLE_RPM, MAX_RPM,
    BASELINE_MAP, BASELINE_FF
)
from physics_model import CYL_TRIM_EGT, CYL_TRIM_CHT


# ── ISA helpers ─────────────────────────────────────────────────────────────
def _isa_density(altitude_ft: float) -> float:
    altitude_m = altitude_ft * FT_TO_M
    T_amb_k = T0 - L * altitude_m
    return math.pow(T_amb_k / T0, 4.256)


def _turbo_boost(altitude_ft: float) -> float:
    """Calculate turbocharger compensation factor based on altitude."""
    if altitude_ft <= CRITICAL_ALTITUDE_FT:
        return 1.0
    excess = altitude_ft - CRITICAL_ALTITUDE_FT
    return max(0.5, 1.0 - excess / 40_000)


def _isa_baselines(altitude_ft: float, throttle_pct: float = 1.0):
    """
    Calculate baseline expected values considering altitude and throttle.
    
    Includes turbocharger compensation to prevent spurious RPM residuals 
    when the system runs at partial throttle.
    """
    density_ratio = _isa_density(altitude_ft)
    boost = _turbo_boost(altitude_ft)

    expected_rpm = max(IDLE_RPM, MAX_RPM * throttle_pct * boost)
    expected_map = max(10.0, BASELINE_MAP * throttle_pct * boost)
    rpm_ratio = min(1.5, max(0.0, expected_rpm / MAX_RPM))
    expected_ff  = BASELINE_FF * throttle_pct * boost * rpm_ratio
    return expected_rpm, expected_map, expected_ff


# ── Feature engineering ──────────────────────────────────────────────────────
def _to_features(rpm, map_v, op, ff, egt, cht, kurtosis,
                 altitude_ft=10_000, throttle_pct=1.0):
    """
    Convert raw telemetry into 7 fault-discriminating features.

    Feature engineering rationale:
      - EGT spread:  misfire drives one cylinder's EGT far above others
      - Mean CHT:    cooling fault raises all cylinders uniformly
      - Kurtosis:    bearing wear drives kurtosis from ~3 toward 6+
      - Oil pressure: cooling fault drops OP from 60 toward 48 psi
      - RPM residual: throttle-aware RPM deviation (misfire causes ~220 RPM sag)
      - MAP residual: misfire causes ~3 inHg rise
      - FF residual:  correlates with RPM/load changes
    """
    exp_rpm, exp_map, exp_ff = _isa_baselines(altitude_ft, throttle_pct)
    return [
        max(egt) - min(egt),          # EGT spread: ~2–4 nominal, >40 on misfire
        sum(cht) / 4.0 - BASELINE_CHT, # Mean CHT deviation: ~0 nominal, >30 on cooling
        kurtosis,                      # Raw kurtosis: ~2.9 nominal, >5 on bearing
        op - MAX_OP,                   # Oil pressure deviation: ~0 nominal, -12 on cooling
        rpm - exp_rpm,                 # RPM deviation from throttle-aware expected
        map_v - exp_map,               # MAP deviation
        ff - exp_ff,                   # Fuel flow deviation
    ]


# ── Training data ────────────────────────────────────────────────────────────
RNG = np.random.default_rng(42)


def _nominal_baselines(n: int = 500) -> np.ndarray:
    """
    Produce *n* synthetic nominal-residual vectors.

    Samples throttle across its operational range [40%, 100%] so the 
    training distribution matches the actual operating envelope.

    Covers:
      - Altitudes 0 – 30 000 ft  (ISA density variation + turbo model)
      - Throttle 40 – 100 %
      - Engine warm-up  (warmup ∈ [0, 1])
      - Sensor noise + governor wander matching main.py
    """
    rows = []
    for _ in range(n):
        altitude_ft  = RNG.uniform(0, 30_000)
        throttle_pct = RNG.uniform(0.4, 1.0)
        warmup       = RNG.uniform(0.0, 1.0)

        exp_rpm, exp_map, exp_ff = _isa_baselines(altitude_ft, throttle_pct)
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

        feats = _to_features(rpm, map_val, op, ff, egt, cht, kurtosis,
                              altitude_ft, throttle_pct)
        rows.append(feats)

    return np.array(rows)


# ── Fit or Load the model at import time ────────────────────────────────────
MODEL_PATH = os.path.join(os.path.dirname(__file__), "models", "isolation_forest.pkl")
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
        contamination=0.002,      # very low: training data is 100 % healthy
        random_state=42,
    )
    _model.fit(_scaled_training)

    # Save to disk
    joblib.dump({"scaler": _scaler, "model": _model}, MODEL_PATH)


# ── Public API ───────────────────────────────────────────────────────────────
def score_snapshot(telemetry: dict) -> dict:
    """
    Score a single telemetry snapshot.

    Parameters
    ----------
    telemetry : dict
        Must contain keys: rpm, map, op, ff, egt (list[4]), cht (list[4]),
        vibration_kurtosis, altitude_ft.
        Optional: throttle (float, 0–100; defaults to 100.0 if absent).

    Returns
    -------
    dict  {"if_label": "NORMAL"|"ANOMALY", "if_score": float}
    """
    # Extract throttle so RPM baseline is correct at partial throttle
    throttle_pct = telemetry.get("throttle", 100.0) / 100.0

    feats = _to_features(
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
