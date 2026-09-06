"""
Shared constants for the UAV Digital Twin simulation.
Centralizes thermodynamic, mechanical, and atmospheric parameters.
"""

# ---------------------------------------------------------------------------
# Unit Conversions
# ---------------------------------------------------------------------------
FT_TO_M = 0.3048

# ---------------------------------------------------------------------------
# Engine Geometry & Mechanics
# ---------------------------------------------------------------------------
CYLINDERS = 4
FIRING_ORDER = [0, 2, 3, 1]
FIRE_CRANK = {c: 180.0 * i for i, c in enumerate(FIRING_ORDER)}
CYCLE_DEG = 720.0

# ---------------------------------------------------------------------------
# Engine Physical Baselines
# ---------------------------------------------------------------------------
BASELINE_EGT = 806.5    # Nominal Exhaust Gas Temperature (°C)
BASELINE_CHT = 91.0     # Nominal Cylinder Head Temperature (°C)
IDLE_RPM = 1000.0       # Minimum engine speed (RPM)
MAX_RPM = 4800.0        # Redline engine speed (RPM)
BASELINE_MAP = 29.92    # Nominal sea-level Manifold Absolute Pressure (inHg)
BASELINE_FF = 8.5       # Nominal Fuel Flow at full throttle, sea level (gal/hr)
MAX_OP = 60.0           # Nominal Oil Pressure at redline RPM (psi)

# ---------------------------------------------------------------------------
# Cylinder Trims & Thermals
# ---------------------------------------------------------------------------
# Time constants for thermal inertia (seconds)
TAU_EGT = 1.0
TAU_CHT = 10.0
CHT_WARMUP_T = 45.0  # Warmup curve time constant

# ---------------------------------------------------------------------------
# Altitude & Atmosphere (ISA)
# ---------------------------------------------------------------------------
T0 = 288.15        # Sea-level standard temp (K)
L = 0.0065         # Lapse rate (K/m)
CRITICAL_ALTITUDE_FT = 18_000  # Turbo fully compensates up to this altitude

# ---------------------------------------------------------------------------
# Simulation Parameters
# ---------------------------------------------------------------------------
FAULT_TAU = 5.0    # Time constant for fault ramp-in (seconds)
