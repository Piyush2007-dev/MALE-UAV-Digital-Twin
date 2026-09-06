from constants import BASELINE_CHT, MAX_OP
from physics.expected import calculate_expected, calculate_expected_map, calculate_expected_fuel_flow

def to_features(rpm, map_v, op, ff, egt, cht, kurtosis, altitude_ft=10_000, throttle_pct=1.0):
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
    exp = calculate_expected(altitude_ft, throttle_pct * 100.0)
    exp_rpm = exp["expected_rpm"]
    exp_map = calculate_expected_map(altitude_ft, throttle_pct * 100.0)
    exp_ff = calculate_expected_fuel_flow(exp_rpm, altitude_ft, throttle_pct * 100.0)
    
    return [
        max(egt) - min(egt),          # EGT spread: ~2–4 nominal, >40 on misfire
        sum(cht) / 4.0 - BASELINE_CHT, # Mean CHT deviation: ~0 nominal, >30 on cooling
        kurtosis,                      # Raw kurtosis: ~2.9 nominal, >5 on bearing
        op - MAX_OP,                   # Oil pressure deviation: ~0 nominal, -12 on cooling
        rpm - exp_rpm,                 # RPM deviation from throttle-aware expected
        map_v - exp_map,               # MAP deviation
        ff - exp_ff,                   # Fuel flow deviation
    ]
