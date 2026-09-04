import math

def calculate_isa(altitude_ft: float):
    """
    Formula A11: International Standard Atmosphere (ISA) Model
    Adjusts ambient temperature and air density based on altitude.
    """
    altitude_m = altitude_ft * 0.3048
    T0 = 288.15  # Sea level standard temp (K)
    L = 0.0065   # Lapse rate (K/m)
    
    # Calculate Ambient Temperature at altitude
    T_amb_k = T0 - (L * altitude_m)
    T_amb_c = T_amb_k - 273.15
    
    # Simple air density penalty multiplier (1.0 at sea level, drops at altitude)
    density_ratio = math.pow((T_amb_k / T0), 4.256)
    
    return T_amb_c, density_ratio

def calculate_expected(altitude_ft: float, throttle: float):
    """
    Calculates expected engine parameters based on physics/steady-state assumptions.
    throttle: 0.0 to 100.0
    """
    throttle_pct = throttle / 100.0
    t_amb_c, density_ratio = calculate_isa(altitude_ft)
    
    # RPM: scales with throttle and air density
    # Base 100% throttle RPM = 4800 at sea level
    expected_rpm = 4800 * density_ratio * throttle_pct
    # Don't let expected RPM drop below idle (e.g., 1000)
    expected_rpm = max(1000, expected_rpm)
    
    # CHT (Cylinder Head Temperature): Rises with RPM/Throttle, falls with altitude (thinner air but much colder)
    # Base CHT around 95C, scales up with throttle to max ~135C
    expected_cht = 95 + (t_amb_c * 0.5) + (40 * throttle_pct)
    
    # EGT (Exhaust Gas Temperature): Shifts with throttle. 
    # High throttle = hotter exhaust, low throttle = cooler.
    # Normal band is 750-850C.
    expected_egt = 750 + (100 * throttle_pct)
    
    return {
        "expected_rpm": expected_rpm,
        "expected_cht": expected_cht,
        "expected_egt": expected_egt
    }
