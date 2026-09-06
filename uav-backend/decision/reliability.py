def get_reliability_tier(reliability_score: float) -> str:
    if reliability_score >= 0.95:
        return "CONTINUE"
    elif reliability_score >= 0.80:
        return "DERATE"
    elif reliability_score >= 0.60:
        return "DIVERT"
    else:
        return "RTB"

def get_suggested_action(tier: str, fault_mode: str) -> str:
    if tier in ["DIVERT", "RTB"]:
        if fault_mode == "misfire":
            return "Cylinder misfire detected. Recommend immediate RTB to prevent total loss of thrust."
        elif fault_mode == "cooling":
            return "Cooling degradation detected. Recommend divert to lower altitude to reduce thermal load."
        elif fault_mode == "bearing":
            return "Bearing wear detected (high vibration). Recommend RTB, avoid high-vibration maneuvers."
        else:
            return "Unknown anomaly detected. Recommend precautionary divert."
    return None

def get_alert_state(fault_mode: str, egt_boost: float, egt_gap: float, max_cht: float, measured_kurtosis: float) -> dict:
    if fault_mode == "misfire" and egt_boost > 4.0:
        return {"title": "SYS WARN: CYL-1 MISFIRE", "desc": f"Cyl-1 EGT {round(egt_gap, 1)}°C above bank average."}
    elif fault_mode == "cooling" and max_cht > 120.0:
        return {"title": "SYS CRIT: THERMAL LIMIT", "desc": "CHT baseline exceeded across all 4 cylinders."}
    elif fault_mode == "bearing" and measured_kurtosis > 5.0:
        return {"title": "SYS WARN: VIBRATION SPIKE", "desc": "Kurtosis > 5.0 at 2x Order frequency."}
    return None
