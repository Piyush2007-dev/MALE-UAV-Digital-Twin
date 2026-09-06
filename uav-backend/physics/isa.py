import math
from constants import T0, L, FT_TO_M

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
