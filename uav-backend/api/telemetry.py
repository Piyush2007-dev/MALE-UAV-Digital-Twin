import time
import math
import random
from fastapi import APIRouter
import state as state_module
from constants import FAULT_TAU, CYLINDERS, FIRE_CRANK, CYCLE_DEG, TAU_EGT, TAU_CHT, CHT_WARMUP_T, BASELINE_EGT, BASELINE_CHT, MAX_OP, BASELINE_MAP, BASELINE_FF
from physics.isa import calculate_isa
from physics.expected import calculate_expected, calculate_expected_map, calculate_expected_oil_pressure, calculate_expected_fuel_flow, CYL_TRIM_EGT, CYL_TRIM_CHT
from physics.fault_modes import get_fault_targets
from ml.isolation_forest import score_snapshot
from ml.classifier import classify_fault
from health.ahp import calculate_composite_hi
from health.rul import calculate_rul_hours, calculate_wear_health, get_wear_rate
from decision.reliability import get_reliability_tier, get_suggested_action, get_alert_state

router = APIRouter()
history_egt = []

def ease(current: float, target: float, rate: float = 0.18) -> float:
    return current + (target - current) * rate

def check_confidence(altitude: float, throttle: float) -> str:
    if 0.0 <= altitude <= 20000.0 and 40.0 <= throttle <= 100.0:
        return "HIGH CONFIDENCE (In Envelope)"
    return "EXTRAPOLATED (Out of Envelope)"

@router.get("/api/telemetry")
def get_telemetry(altitude: float = 10000, throttle: float = 100.0, fault_mode: str = "normal"):
    state = state_module.state  # always dereference through the module so reset() is visible
    now = time.monotonic()
    if state.last_poll_s is None:
        state.last_poll_s = now
    dt = min(max(now - state.last_poll_s, 0.05), 5.0)
    state.last_poll_s = now
    state.sim_time_s += dt

    fault_ease_rate = 1.0 - math.exp(-dt / FAULT_TAU)

    t_amb_c, density_ratio = calculate_isa(altitude)
    expected_metrics = calculate_expected(altitude, throttle, state.sim_time_s)
    expected_rpm = expected_metrics["expected_rpm"]

    # ── Fault target deltas ────────────────────────────────────────────────
    targets = get_fault_targets(fault_mode)
    
    state.cumulative_wear += targets["wear"]
    egt_target = targets["egt"]
    cht_target = targets["cht"]
    kurt_target = targets["kurt"]
    op_target = targets["op"]
    rpm_target = targets["rpm"]
    map_target = targets["map"]

    state.egt_boost   = ease(state.egt_boost,   egt_target,  fault_ease_rate)
    state.cht_boost   = ease(state.cht_boost,   cht_target,  fault_ease_rate)
    state.kurt_boost  = ease(state.kurt_boost,  kurt_target, fault_ease_rate)
    state.op_drop     = ease(state.op_drop,     op_target,   fault_ease_rate)
    state.rpm_penalty = ease(state.rpm_penalty, rpm_target,  fault_ease_rate)
    state.map_boost   = ease(state.map_boost,   map_target,  fault_ease_rate)

    # ── Wander ────────────────────────────────────────────────
    state.load_wander = state.load_wander * 0.94 + random.uniform(-3.0, 3.0)
    state.kurt_wander = max(-0.05, min(0.05, state.kurt_wander * 0.9 + random.uniform(-0.008, 0.008)))

    # ── RPM ───────────────────────────────────────────────────────────────
    rpm_now      = expected_rpm - state.rpm_penalty + state.load_wander
    firing_rate  = max(0.0, rpm_now / 120.0)

    # ── Crank advance ─────────────────────────────────────────────────────
    state.crank_deg = (state.crank_deg + rpm_now * 6.0 * dt) % CYCLE_DEG
    for c in range(CYLINDERS):
        offset = CYCLE_DEG - FIRE_CRANK[c]
        wraps  = math.floor((state.crank_deg + offset) / CYCLE_DEG)
        if wraps > state.fire_count[c]:
            state.fire_count[c] = wraps

    # ── EGT / CHT thermal model ───────────────────────────────────────────
    egt_decay = math.exp(-dt / TAU_EGT)
    cht_decay = math.exp(-dt / TAU_CHT)
    warmup    = 1.0 - math.exp(-state.sim_time_s / CHT_WARMUP_T)

    for c in range(CYLINDERS):
        state.egt_wander[c] = max(-3.0, min(3.0, state.egt_wander[c] * 0.985 + random.uniform(-0.3, 0.3)))
        state.cht_wander[c] = max(-1.4, min(1.4, state.cht_wander[c] * 0.99  + random.uniform(-0.12, 0.12)))

        egt_target_c = (BASELINE_EGT + firing_rate * 0.16 + CYL_TRIM_EGT[c] * warmup 
                        + state.egt_wander[c] + (state.egt_boost if c == 0 else 0.0))
        state.egt_state[c] = ease(state.egt_state[c], egt_target_c, 1.0 - egt_decay)

        cht_target_c = (BASELINE_CHT + firing_rate * 0.05 + CYL_TRIM_CHT[c] + 2.2 * warmup
                        + state.cht_wander[c] + state.cht_boost)
        state.cht_state[c] = ease(state.cht_state[c], cht_target_c, 1.0 - cht_decay)

    # ── Measured values ───────────────────────────────────────────────────
    measured_egt = [e + random.uniform(-0.4, 0.4) for e in state.egt_state]
    measured_egt[0] += state.egt_boost
    measured_cht     = [c + random.uniform(-0.3, 0.3) for c in state.cht_state]

    measured_map      = calculate_expected_map(altitude, throttle) + state.map_boost + random.uniform(-0.1, 0.1)
    measured_op       = MAX_OP - state.op_drop  + random.uniform(-0.4, 0.4)
    measured_ff       = calculate_expected_fuel_flow(rpm_now, altitude, throttle) + random.uniform(-0.04, 0.04)
    measured_kurtosis = 2.9 + state.kurt_wander + state.kurt_boost + random.uniform(-0.02, 0.02)

    vibration_fft = [
        {"order": "0.5x", "amp": round(0.1  + random.uniform(0, 0.02), 2)},
        {"order": "1x",   "amp": round(0.42 + firing_rate * 0.012 + random.uniform(-0.02, 0.02), 2)},
        {"order": "2x",   "amp": round(0.3  + state.kurt_boost * 0.8 + random.uniform(0, 0.03), 2)},
        {"order": "3x",   "amp": round(0.15 + firing_rate * 0.001 + random.uniform(0, 0.02), 2)},
    ]

    # ── Residuals ─────────────────────────────────────────────────────────
    egt_spread = round(max(measured_egt) - min(measured_egt), 1)
    cht_spread = round(max(measured_cht) - min(measured_cht), 1)

    residuals = {
        "rpm":        round(rpm_now           - expected_metrics["expected_rpm"]),
        "egt":        round(measured_egt[0]   - expected_metrics["expected_egt"]),
        "cht":        round(measured_cht[0]   - expected_metrics["expected_cht"]),
        "egt_spread": egt_spread,
        "cht_spread": cht_spread,
        "map":        round(measured_map - calculate_expected_map(altitude, throttle),          2),
        "op":         round(measured_op  - calculate_expected_oil_pressure(rpm_now),  2),
        "ff":         round(measured_ff  - calculate_expected_fuel_flow(rpm_now, altitude, throttle), 3),
    }

    # ── EGT history & z-score ─────────────────────────────────────────────
    history_egt.append(measured_egt[0])
    if len(history_egt) > 30:
        history_egt.pop(0)

    z_score_val = 0.0
    if len(history_egt) == 30:
        mean_egt  = sum(history_egt) / len(history_egt)
        variance  = sum((x - mean_egt) ** 2 for x in history_egt) / len(history_egt)
        std_dev   = math.sqrt(variance) if variance > 0 else 1.0
        z_score_val = abs(measured_egt[0] - mean_egt) / std_dev

    # ── ML anomaly score ──────────────────────────────────────────────────
    snapshot_telemetry = {
        "rpm":               rpm_now,
        "map":               measured_map,
        "op":                measured_op,
        "ff":                measured_ff,
        "egt":               measured_egt,
        "cht":               measured_cht,
        "vibration_kurtosis": measured_kurtosis,
        "altitude_ft":       altitude,
        "throttle":          throttle,
    }
    if_result = score_snapshot(snapshot_telemetry)
    # Map raw IF score to 0.0-1.0 to preserve backward compat with ml_anomaly_score
    ml_anomaly_score = max(0.0, min(1.0, 0.5 - if_result["if_score"] * 2))
    
    ml_anomaly_reason = classify_fault(snapshot_telemetry, if_result["if_label"])

    egt_gap    = measured_egt[0] - max(measured_egt[1:])
    is_anomaly = (
        (ml_anomaly_score > 0.5)
        or (z_score_val > 3.0)
        or egt_gap > 4.0
        or max(measured_cht) > 120.0
        or measured_kurtosis > 5.0
    )

    # ── Wear & RUL ───────────────────────────────────────────────────────
    wear_rate = get_wear_rate(fault_mode)
    state.accumulated_wear_time += wear_rate * dt
    state.operating_hours       += dt / 3600.0

    wear_health = calculate_wear_health(state.accumulated_wear_time)
    
    health_index = calculate_composite_hi(wear_health, ml_anomaly_score, residuals, measured_kurtosis)
    rul_hours = calculate_rul_hours(state.accumulated_wear_time, wear_rate)

    tier = get_reliability_tier(health_index / 100.0)
    suggested_action = get_suggested_action(tier, fault_mode)
    alert_state = get_alert_state(fault_mode, state.egt_boost, egt_gap, max(measured_cht), measured_kurtosis)

    return {
        "timestamp": time.strftime("%H:%M:%S"),
        "hex_id":    f"0x{random.randint(0, 16777215):06X}",
        "environment": {
            "altitude_ft":       altitude,
            "throttle_pct":      throttle,
            "ambient_temp_c":    round(t_amb_c, 1),
            "air_density_ratio": round(density_ratio, 3),
            "confidence_status": check_confidence(altitude, throttle),
        },
        "engine": {
            "rpm":               round(rpm_now + random.uniform(-1, 1)),
            "map":               round(measured_map, 1),
            "op":                round(measured_op, 1),
            "ff":                round(measured_ff, 1),
            "egt":               [round(e, 1) for e in measured_egt],
            "cht":               [round(c, 1) for c in measured_cht],
            "vibration_kurtosis": round(measured_kurtosis, 2),
        },
        "expected": {
            "rpm": round(expected_metrics["expected_rpm"]),
            "egt": round(expected_metrics["expected_egt"]),
            "cht": round(expected_metrics["expected_cht"]),
            "map": round(calculate_expected_map(altitude, throttle), 1),
            "op":  round(calculate_expected_oil_pressure(rpm_now), 1),
            "ff":  round(calculate_expected_fuel_flow(rpm_now, altitude, throttle), 2),
        },
        "residuals": residuals,
        "vibration_fft": vibration_fft,
        "analytics": {
            "z_score":          round(z_score_val, 2),
            "ml_anomaly_score": round(ml_anomaly_score, 3),
            "anomaly_reason":   ml_anomaly_reason,
            "is_anomaly":       is_anomaly,
            "health_index":     round(health_index),
            "rul_hours":        round(rul_hours),
            "mission_tier":     tier,
            "suggested_action": suggested_action,
            "isolation_forest": if_result,
            "alert": alert_state,
        },
    }
