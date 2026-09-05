"""
Isolation Forest anomaly pre-filter for the MALE-UAV Digital Twin.

Trains once at import time on synthetic *nominal* telemetry residuals
(deviations from the ISA-predicted baseline), then exposes a single
function ``score_snapshot(telemetry)`` that returns a label + score
for each live snapshot.

This module runs **alongside** the existing threshold-based anomaly
detection — it does not replace or modify it.
"""

import math
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler

# ── Altitude-based baseline (same ISA model as main.py) ─────────────────
_T0 = 288.15
_L  = 0.0065


def _isa_baselines(altitude_ft: float):
    """Return (expected_rpm, expected_map, expected_ff) at the given altitude."""
    altitude_m = altitude_ft * 0.3048
    T_amb_k = _T0 - _L * altitude_m
    density_ratio = math.pow(T_amb_k / _T0, 4.256)
    expected_rpm = 4800.0 * density_ratio
    expected_map = 29.92 * density_ratio
    expected_ff  = 8.5 * density_ratio
    return expected_rpm, expected_map, expected_ff


def _to_features(rpm, map_v, op, ff, egt, cht, kurtosis, altitude_ft=10_000):
    """Convert raw telemetry into fault-discriminating features (7-dim).

    Feature engineering rationale:
      - EGT spread:  misfire drives one cylinder's EGT far above others
      - Mean CHT:    cooling fault raises all cylinders uniformly
      - Kurtosis:    bearing wear drives kurtosis from ~3 toward 6+
      - Oil pressure: cooling fault drops OP from 60 toward 48 psi
      - RPM residual: misfire causes ~220 RPM sag
      - MAP residual: misfire causes ~3 inHg rise
      - FF residual:  correlates with RPM/load changes
    """
    exp_rpm, exp_map, exp_ff = _isa_baselines(altitude_ft)
    return [
        max(egt) - min(egt),         # EGT spread: ~2-4 nominal, >40 on misfire
        sum(cht) / 4.0 - 93.0,      # Mean CHT deviation: ~0 nominal, >30 on cooling
        kurtosis,                     # Raw kurtosis: ~2.9 nominal, >5 on bearing
        op - 60.0,                    # Oil pressure deviation: ~0 nominal, -12 on cooling
        rpm - exp_rpm,                # RPM deviation from ISA expected
        map_v - exp_map,              # MAP deviation
        ff - exp_ff,                  # Fuel flow deviation
    ]



# ── Generate nominal training data ──────────────────────────────────────
_RNG = np.random.default_rng(42)


def _nominal_baselines(n: int = 500) -> np.ndarray:
    """Produce *n* synthetic nominal-residual vectors.

    Covers the full operating envelope:
      - Altitudes 0 – 30 000 ft  (ISA density variation)
      - Engine warm-up  (warmup ∈ [0, 1])
      - Sensor noise + governor wander matching main.py
    """
    rows = []
    for _ in range(n):
        altitude_ft = _RNG.uniform(0, 30_000)
        warmup = _RNG.uniform(0.0, 1.0)

        exp_rpm, exp_map, exp_ff = _isa_baselines(altitude_ft)
        load_wander = _RNG.uniform(-3.0, 3.0)

        rpm = exp_rpm + load_wander + _RNG.uniform(-1, 1)
        map_val = exp_map + _RNG.uniform(-0.1, 0.1)
        op = 60.0 + _RNG.uniform(-0.4, 0.4)
        ff = exp_ff * (rpm / exp_rpm) + _RNG.uniform(-0.04, 0.04)

        firing_rate = max(0.0, rpm / 120.0)
        cyl_trim_egt = [2.0, -1.2, 0.5, -1.3]
        cyl_trim_cht = [0.9, -0.7, 0.4, -0.6]

        egt = [
            806.5 + firing_rate * 0.16 + cyl_trim_egt[c] * warmup
            + _RNG.uniform(-3.0, 3.0) + load_wander * 0.010
            + _RNG.uniform(-0.4, 0.4)
            for c in range(4)
        ]
        cht = [
            91.0 + firing_rate * 0.05 + cyl_trim_cht[c] + 2.2 * warmup
            + _RNG.uniform(-1.4, 1.4) + _RNG.uniform(-0.3, 0.3)
            for c in range(4)
        ]
        kurtosis = 2.9 + _RNG.uniform(-0.05, 0.05) + _RNG.uniform(-0.02, 0.02)

        feats = _to_features(rpm, map_val, op, ff, egt, cht, kurtosis,
                              altitude_ft)
        rows.append(feats)

    return np.array(rows)


# ── Fit the model at import time ────────────────────────────────────────
_training_data = _nominal_baselines(1000)          # more training samples
_scaler = StandardScaler().fit(_training_data)
_scaled_training = _scaler.transform(_training_data)

_model = IsolationForest(
    n_estimators=200,
    contamination=0.002,      # very low: training data is 100% healthy
    random_state=42,
)
_model.fit(_scaled_training)


# ── Public API ──────────────────────────────────────────────────────────
def score_snapshot(telemetry: dict) -> dict:
    """Score a single telemetry snapshot.

    Parameters
    ----------
    telemetry : dict
        Must contain keys: rpm, map, op, ff, egt (list[4]), cht (list[4]),
        vibration_kurtosis, altitude_ft.

    Returns
    -------
    dict  {"if_label": "NORMAL"|"ANOMALY", "if_score": float}
    """
    feats = _to_features(
        telemetry["rpm"],
        telemetry["map"],
        telemetry["op"],
        telemetry["ff"],
        telemetry["egt"],
        telemetry["cht"],
        telemetry["vibration_kurtosis"],
        telemetry.get("altitude_ft", 10_000),
    )
    features = _scaler.transform(np.array([feats]))

    prediction = _model.predict(features)[0]
    raw_score  = float(_model.score_samples(features)[0])

    return {
        "if_label": "NORMAL" if prediction == 1 else "ANOMALY",
        "if_score": round(raw_score, 4),
    }

