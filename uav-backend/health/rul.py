import math

def get_wear_rate(fault_mode: str) -> float:
    return {
        "normal":  1.0,
        "misfire": 15.0,
        "cooling": 10.0,
        "bearing": 25.0,
    }.get(fault_mode, 1.0)

def calculate_wear_health(accumulated_wear_time: float, theta_1: float = 0.01, theta_2: float = 0.001) -> float:
    t = accumulated_wear_time
    # Use (exp(theta_2*t) - 1) so the degradation starts at exactly 0 when t=0,
    # giving wear_health = 1.0 (100%) on a fresh / just-reset engine.
    return max(0.0, 1.0 - (theta_1 * (math.exp(theta_2 * t) - 1.0)))

def calculate_rul_hours(accumulated_wear_time: float, current_wear_rate: float, theta_1: float = 0.01, theta_2: float = 0.001) -> float:
    t = accumulated_wear_time
    try:
        t_end = math.log(1.0 / theta_1) / theta_2
        rul_effective_time_remaining = max(0.0, t_end - t)
        rul_hours = rul_effective_time_remaining / max(current_wear_rate, 0.001)
    except ValueError:
        rul_hours = 0.0
    return rul_hours
