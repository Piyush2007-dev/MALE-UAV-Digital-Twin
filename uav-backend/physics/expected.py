import math
from constants import (
    IDLE_RPM, MAX_RPM, CHT_WARMUP_T, BASELINE_CHT, BASELINE_EGT,
    BASELINE_MAP, MAX_OP, BASELINE_FF
)
from physics.isa import calculate_isa
from physics.turbo import _turbo_boost_compensation

# Fixed baseline offsets per cylinder to simulate normal variation
CYL_TRIM_EGT = [2.0, -1.2, 0.5, -1.3]
CYL_TRIM_CHT = [0.9, -0.7, 0.4, -0.6]


def calculate_expected(altitude_ft: float, throttle: float,
                       sim_time_s: float = 0.0, warmup_tau: float = CHT_WARMUP_T):
    """
    Calculate expected engine parameters for a healthy, fully-functional engine.
    """
    throttle_pct = throttle / 100.0
    t_amb_c, density_ratio = calculate_isa(altitude_ft)

    boost = _turbo_boost_compensation(altitude_ft)
    expected_rpm = max(IDLE_RPM, MAX_RPM * throttle_pct * boost)

    firing_rate = max(0.0, expected_rpm / 120.0)
    warmup = 1.0 - math.exp(-sim_time_s / warmup_tau)

    expected_cht = BASELINE_CHT + firing_rate * 0.05 + 2.2 * warmup
    expected_egt = BASELINE_EGT + firing_rate * 0.16

    return {
        "expected_rpm": expected_rpm,
        "expected_cht": expected_cht,
        "expected_egt": expected_egt,
    }


def calculate_expected_map(altitude_ft: float, throttle: float) -> float:
    boost = _turbo_boost_compensation(altitude_ft)
    throttle_pct = throttle / 100.0
    return max(10.0, BASELINE_MAP * throttle_pct * boost)


def calculate_expected_oil_pressure(rpm: float) -> float:
    return MAX_OP * min(1.0, max(0.0, rpm / MAX_RPM))


def calculate_expected_fuel_flow(rpm: float, altitude_ft: float, throttle: float) -> float:
    boost = _turbo_boost_compensation(altitude_ft)
    throttle_pct = throttle / 100.0
    rpm_ratio = min(1.5, max(0.0, rpm / MAX_RPM))
    return BASELINE_FF * throttle_pct * boost * rpm_ratio
