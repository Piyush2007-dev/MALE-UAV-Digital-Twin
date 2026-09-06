from constants import CRITICAL_ALTITUDE_FT

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
