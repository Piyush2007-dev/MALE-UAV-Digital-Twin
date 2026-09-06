def calculate_composite_hi(wear_health: float, ml_anomaly_score: float, residuals: dict, measured_kurtosis: float) -> float:
    """
    Calculate AHP-Enhanced Composite Health Index.
    
    AHP Weighting Rationale:
    1. Wear Formula (0.50) — Most direct representation of accumulated degradation.
    2. ML Anomaly Score (0.25) — Isolation forest screen for non-linear interactions.
    3. Physics Residuals (0.15) — Deviation from expected thermodynamic behaviour.
    4. Vibration Kurtosis (0.10) — Specific mechanical/bearing wear indicator.
    """
    anomaly_health = max(0.0, 1.0 - ml_anomaly_score)

    res_mag = (abs(residuals["rpm"]) / 20.0 + abs(residuals["egt"]) / 10.0 + abs(residuals["cht"]) / 5.0) / 3.0
    physics_health = max(0.0, 1.0 - (res_mag / 2.0))

    kurt_dev = abs(measured_kurtosis - 2.9)
    vibration_health = max(0.0, 1.0 - (kurt_dev / 2.1))

    composite_hi_val = (
        0.50 * wear_health
        + 0.25 * anomaly_health
        + 0.15 * physics_health
        + 0.10 * vibration_health
    )
    return composite_hi_val * 100.0
