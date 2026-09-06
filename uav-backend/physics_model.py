import math
from constants import (
    CRITICAL_ALTITUDE_FT, CHT_WARMUP_T, T0, L, FT_TO_M,
    BASELINE_EGT, BASELINE_CHT, IDLE_RPM, MAX_RPM,
    BASELINE_MAP, BASELINE_FF, MAX_OP
)
# ---------------------------------------------------------------------------
# Constants & Baselines
# ---------------------------------------------------------------------------
# Fixed baseline offsets per cylinder to simulate normal variation
CYL_TRIM_EGT = [2.0, -1.2, 0.5, -1.3]
CYL_TRIM_CHT = [0.9, -0.7, 0.4, -0.6]
# ---------------------------------------------------------------------------
# ISA atmosphere
# ---------------------------------------------------------------------------
def calculate_isa(altitude_ft: float):
    """
    Calculate the International Standard Atmosphere (ISA) conditions for a given altitude.
    Uses Formula A11 to adjust ambient temperature and air density based on altitude,
    assuming standard sea-level conditions (15°C, 1013.25 hPa).
    Args:
        altitude_ft (float): Pressure altitude in feet. 
    Returns:
        tuple: (ambient_temperature_celsius, air_density_ratio)
    """
    altitude_m = altitude_ft * FT_TO_M

    T_amb_k = T0 - (L * altitude_m)
    T_amb_c = T_amb_k - 273.15

    density_ratio = math.pow((T_amb_k / T0), 4.256)
    return T_amb_c, density_ratio


# ---------------------------------------------------------------------------
# Turbocharger compensation
# ---------------------------------------------------------------------------
def _turbo_boost_compensation(altitude_ft: float) -> float:
    """
    Calculate turbocharger efficiency multiplier based on altitude.
    A turbocharger maintains sea-level manifold pressure up to its critical 
    altitude. Above this altitude, the air becomes too thin for the compressor 
    to maintain full boost, resulting in a gradual fall-off in power.
    Args:
        altitude_ft (float): Current altitude in feet. 
    Returns:
        float: Efficiency multiplier between 0.5 (maximum fall-off) and 1.0 (full boost).
    """
    if altitude_ft <= CRITICAL_ALTITUDE_FT:
        return 1.0
    excess = altitude_ft - CRITICAL_ALTITUDE_FT
    return max(0.5, 1.0 - excess / 40_000)

# ---------------------------------------------------------------------------
# Primary expected-metrics function (used by main.py + ml_model.py)
# ---------------------------------------------------------------------------
def calculate_expected(altitude_ft: float, throttle: float,
                       sim_time_s: float = 0.0, warmup_tau: float = CHT_WARMUP_T):
    """
    Calculate expected engine parameters for a healthy, fully-functional engine.
    These baseline expectations are used to generate residuals (deviations) 
    that the anomaly detection models use to identify faults. The calculations 
    account for environmental factors (ISA atmosphere), mechanical systems 
    (turbocharger boost), and thermal transients (engine warmup phase).
    Args:
        altitude_ft (float): Pressure altitude in feet.
        throttle (float): Throttle position command (0.0 to 100.0 %).
        sim_time_s (float): Elapsed simulation time in seconds, used to calculate thermal warmup.
        warmup_tau (float): CHT warm-up time constant in seconds.
    Returns:
        dict: Expected values for RPM, Cylinder Head Temperature (CHT), and Exhaust Gas Temperature (EGT).
    """
    throttle_pct = throttle / 100.0
    t_amb_c, density_ratio = calculate_isa(altitude_ft)

    # Turbo-aware RPM calculation based on density and boost
    boost = _turbo_boost_compensation(altitude_ft)
    expected_rpm = max(IDLE_RPM, MAX_RPM * throttle_pct * boost)

    # Rebase thermal calculations on expected_rpm (firing rate) instead of direct throttle
    firing_rate = max(0.0, expected_rpm / 120.0)

    # Thermal warmup transient factor
    warmup = 1.0 - math.exp(-sim_time_s / warmup_tau)

    # Calculate expected CHT (assuming healthy, balanced cylinders where trims average to 0)
    expected_cht = BASELINE_CHT + firing_rate * 0.05 + 2.2 * warmup

    # Calculate expected EGT (similarly, assuming healthy, balanced cylinders)
    expected_egt = BASELINE_EGT + firing_rate * 0.16

    return {
        "expected_rpm": expected_rpm,
        "expected_cht": expected_cht,
        "expected_egt": expected_egt,
    }


# ---------------------------------------------------------------------------
# Expected secondary metrics
# ---------------------------------------------------------------------------
def calculate_expected_map(altitude_ft: float) -> float:
    """
    Calculate expected Manifold Absolute Pressure (MAP).
    Note: The current primary simulation (in main.py) generates MAP 
    as a naturally-aspirated value. This function mirrors that simulation 
    logic so that residuals remain zero-centered.
    Args:
        altitude_ft (float): Pressure altitude in feet.
    Returns:
        float: Expected MAP in inches of Mercury (inHg).
    """
    _, density_ratio = calculate_isa(altitude_ft)
    return BASELINE_MAP * density_ratio


def calculate_expected_oil_pressure(rpm: float) -> float:
    """
    Calculate expected oil pressure for a healthy engine.
    The oil pump is mechanically engine-driven, meaning pressure scales 
    linearly with RPM up to the redline.
    - Idle (1,000 RPM) -> ~12.5 psi
    - Redline (4,800 RPM) -> 60.0 psi
    Args:
        rpm (float): Current engine RPM.
    Returns:
        float: Expected oil pressure in psi.
    """
    return MAX_OP * min(1.0, max(0.0, rpm / MAX_RPM))


def calculate_expected_fuel_flow(rpm: float, altitude_ft: float) -> float:
    """
    Calculate expected volumetric fuel flow.
    Models fuel flow based on air density and engine speed.
    Args:
        rpm (float): Current engine RPM.
        altitude_ft (float): Pressure altitude in feet.
    Returns:
        float: Expected fuel flow in gallons per hour (gal/hr).
    """
    _, density_ratio = calculate_isa(altitude_ft)
    # Avoid division by zero at startup; clamp ratio to sane range
    rpm_ratio = min(1.5, max(0.0, rpm / MAX_RPM))
    return BASELINE_FF * density_ratio * rpm_ratio
