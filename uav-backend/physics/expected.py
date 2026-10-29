import math
from constants import (
    IDLE_RPM, MAX_RPM, CHT_WARMUP_T, BASELINE_CHT, BASELINE_EGT,
    BASELINE_MAP, MAX_OP, BASELINE_FF, CRITICAL_ALTITUDE_FT
)
from physics.isa import calculate_isa

# Engine geometry constants (Austro AE300 / generic 2.0L diesel as per PRD)
V_D = 0.0005 # Displacement volume per cylinder (m^3)
V_IM = 0.002 # Intake manifold volume (m^3)
R_AIR = 287.058 # Specific gas constant for air (J/(kg K))
GAMMA = 1.4 # Ratio of specific heats
BORE = 0.0822 # Cylinder bore diameter (m)
STROKE = 0.0924 # Piston stroke (m)

# Woschni/Wiebe constants
WIEBE_A1 = 5.0
WIEBE_M1 = 2.0
WOSCHNI_C1 = 2.28
WOSCHNI_C2 = 3.24e-3

# Fixed baseline offsets per cylinder to simulate normal variation
CYL_TRIM_EGT = [2.0, -1.2, 0.5, -1.3]
CYL_TRIM_CHT = [0.9, -0.7, 0.4, -0.6]

def _turbo_compressor_pressure_ratio(altitude_ft: float, throttle_pct: float) -> float:
    """Formula A9: Turbocharger Compressor Pressure Ratio (Pi_c)."""
    # Simplified isentropic expansion to determine available boost
    t_amb_c, density_ratio = calculate_isa(altitude_ft)
    p_amb = 101.325 * density_ratio # Approx ambient pressure in kPa
    
    # The turbo attempts to maintain sea-level MAP (approx 100-140 kPa)
    target_map_kpa = BASELINE_MAP * 3.386 * throttle_pct # convert inHg to kPa
    
    # Pi_c = P_02 / P_01
    # If ambient is too low (high altitude), turbo maxes out its pressure ratio
    max_pi_c = 3.2 # max physical pressure ratio of the compressor
    pi_c = target_map_kpa / max(1.0, p_amb)
    
    return min(pi_c, max_pi_c)

def _mvem_manifold_pressure_derivative(p_im: float, rpm: float, throttle_pct: float, pi_c: float, t_amb_k: float) -> float:
    """Formula A2: MVEM Intake Manifold Pressure Differential Equation (dP_im/dt)."""
    # m_dot_in = mass flow rate through throttle/compressor
    # m_dot_out = mass flow rate swallowed by cylinders (Speed-Density equation)
    
    # Compressor flow map approximation
    p_02 = pi_c * (101325 * math.exp(-0.000118 * 0)) # Base pressure 
    # Simplified mass flows for real-time integration
    m_in = 0.05 * throttle_pct * pi_c
    m_out = (p_im * V_D * (rpm / 60.0)) / (R_AIR * t_amb_k) # Speed-density
    
    dp_im_dt = (R_AIR * t_amb_k / V_IM) * (m_in - m_out)
    return dp_im_dt

def _woschni_heat_transfer_coefficient(crank_deg: float, rpm: float, p_cyl: float, t_cyl: float) -> float:
    """Formula A8: Woschni Convective Heat Transfer Coefficient (h_c)."""
    s_p = 2 * STROKE * (rpm / 60.0) # Mean piston speed
    # h_c = 3.26 * B^(-0.2) * P^0.8 * T^(-0.53) * [C1 * S_p + ...]^0.8
    # Simplified motored pressure differential term for real-time
    velocity_term = WOSCHNI_C1 * s_p
    h_c = 3.26 * (BORE ** -0.2) * (p_cyl ** 0.8) * (t_cyl ** -0.53) * (velocity_term ** 0.8)
    return h_c

def _double_wiebe_mass_fraction(theta: float) -> float:
    """Formula A7: Double-Wiebe Combustion Function (x_b)."""
    # Assuming start of combustion theta_0 = 350 deg (near TDC)
    theta_0 = 350.0
    delta_theta = 40.0
    if theta < theta_0 or theta > theta_0 + delta_theta:
        return 0.0 if theta < theta_0 else 1.0
    
    norm_theta = (theta - theta_0) / delta_theta
    # Simplified single-phase for real-time (beta_w = 1.0)
    x_b = 1.0 - math.exp(-WIEBE_A1 * (norm_theta ** (WIEBE_M1 + 1)))
    return x_b

def calculate_expected(state, altitude_ft: float, throttle: float, dt: float):
    """
    Calculate expected engine parameters using literal differential integration.
    """
    throttle_pct = throttle / 100.0
    t_amb_c, density_ratio = calculate_isa(altitude_ft)
    t_amb_k = t_amb_c + 273.15
    
    # 1. Turbocharger & Manifold (Formulas A9 & A2)
    pi_c = _turbo_compressor_pressure_ratio(altitude_ft, throttle_pct)
    # Integrate MVEM
    expected_rpm = max(IDLE_RPM, MAX_RPM * throttle_pct * (pi_c / 1.5))
    rpm_state = expected_rpm # Simplified governor
    
    dp_dt = _mvem_manifold_pressure_derivative(state.expected_map_state * 3386.39, rpm_state, throttle_pct, pi_c, t_amb_k)
    # Convert Pa back to inHg
    state.expected_map_state += (dp_dt / 3386.39) * dt
    
    # Bound it to reasonable limits
    state.expected_map_state = max(10.0, min(50.0, state.expected_map_state))

    # 2. In-Cylinder Combustion & Heat Transfer (Formulas A7 & A8)
    # Get current mass fraction burned
    x_b = _double_wiebe_mass_fraction(state.crank_deg % 720.0)
    
    # Estimate instantaneous in-cylinder pressure and temp based on combustion
    p_cyl = (state.expected_map_state * 3.386) * (1.0 + 10.0 * x_b) # kPa
    t_cyl = t_amb_k * (1.0 + 4.0 * x_b) # Kelvin
    
    # Woschni heat transfer
    h_c = _woschni_heat_transfer_coefficient(state.crank_deg, rpm_state, p_cyl, t_cyl)
    
    # Translate instantaneous heat transfer into lumped CHT/EGT targets
    firing_rate = max(0.0, rpm_state / 120.0)
    # CHT rises as a function of convective heat transfer h_c
    target_cht = BASELINE_CHT + (h_c * 0.05) * firing_rate
    # EGT is driven by exhaust blowdown temperature (related to combustion completion x_b)
    target_egt = BASELINE_EGT + (t_cyl * 0.15) * firing_rate
    
    # Integrate thermal masses
    state.expected_cht_state += (target_cht - state.expected_cht_state) * (dt / CHT_WARMUP_T)
    state.expected_egt_state += (target_egt - state.expected_egt_state) * (dt / 2.0)
    
    return {
        "expected_rpm": rpm_state,
        "expected_cht": state.expected_cht_state,
        "expected_egt": state.expected_egt_state,
    }

def calculate_expected_map(state, altitude_ft: float, throttle: float) -> float:
    # Now pulled directly from the integrated state
    return state.expected_map_state

def calculate_expected_oil_pressure(rpm: float) -> float:
    return MAX_OP * min(1.0, max(0.0, rpm / MAX_RPM))

def calculate_expected_fuel_flow(rpm: float, altitude_ft: float, throttle: float) -> float:
    # A10: Fuel-Air Equivalence Ratio (simplified for fuel flow)
    throttle_pct = throttle / 100.0
    rpm_ratio = min(1.5, max(0.0, rpm / MAX_RPM))
    t_amb_c, density_ratio = calculate_isa(altitude_ft)
    
    return BASELINE_FF * throttle_pct * density_ratio * rpm_ratio
