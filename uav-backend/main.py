from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import math
import random
import time
from pydantic import BaseModel
from physics_model import calculate_isa, calculate_expected
from ml_model import detector

app = FastAPI(title="MALE UAV Digital Twin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
)

# ---------------------------------------------------------------------------
# 4-cylinder, 4-stroke (Otto) cycle model
# ---------------------------------------------------------------------------
CYLINDERS = 4
FIRING_ORDER = [0, 2, 3, 1]
FIRE_CRANK = {c: 180.0 * i for i, c in enumerate(FIRING_ORDER)}
CYCLE_DEG = 720.0

CYL_TRIM_EGT = [2.0, -1.2, 0.5, -1.3]
CYL_TRIM_CHT = [0.9, -0.7, 0.4, -0.6]

TAU_EGT = 1.0
TAU_CHT = 10.0
CHT_WARMUP_T = 45.0


class EngineState:
    """State carried between API calls: wear bookkeeping + engine-cycle state."""

    def __init__(self):
        self.cumulative_wear = 0.0
        self.operating_hours = 0.0
        self.accumulated_wear_time = 0.0

        self.egt_boost = 0.0
        self.cht_boost = 0.0
        self.kurt_boost = 0.0
        self.op_drop = 0.0
        self.rpm_penalty = 0.0
        self.map_boost = 0.0

        self.sim_time_s = 0.0
        self.last_poll_s = None
        self.crank_deg = random.uniform(0.0, CYCLE_DEG)
        self.fire_count = [0, 0, 0, 0]
        self.egt_state = [806.0, 806.0, 806.0, 806.0]
        self.cht_state = [91.0, 91.0, 91.0, 91.0]
        self.egt_wander = [random.uniform(-1.6, 1.6) for _ in range(CYLINDERS)]
        self.cht_wander = [random.uniform(-0.9, 0.9) for _ in range(CYLINDERS)]
        self.load_wander = 0.0
        self.kurt_wander = 0.0


state = EngineState()
history_egt = []


def ease(current: float, target: float, rate: float = 0.18) -> float:
    return current + (target - current) * rate


class CopilotRequest(BaseModel):
    query: str
    context: dict
    fault_mode: str


@app.post("/api/copilot")
def ask_copilot(req: CopilotRequest):
    query = req.query.lower()
    ctx = req.context
    fault = req.fault_mode

    tier = ctx.get("analytics", {}).get("mission_tier", "UNKNOWN")
    cht = ctx.get("engine", {}).get("cht", [0])[0]
    egt = ctx.get("engine", {}).get("egt", [0])[0]
    rpm = ctx.get("engine", {}).get("rpm", 0)

    answer = "I'm monitoring the digital twin. What would you like to know?"

    if "why" in query and ("divert" in query or "rtb" in query or "recommend" in query):
        if tier in ["DIVERT", "RTB"]:
            if fault == "misfire":
                answer = f"I recommended {tier} because I detected a severe misfire anomaly. Cylinder 1 EGT is currently {egt}°C (expected ~850°C) and RPM has dropped to {rpm}. This indicates a critical loss of combustion."
            elif fault == "cooling":
                answer = f"I recommended {tier} due to thermal degradation. The baseline CHT has spiked to {cht}°C, which exceeds the safe operating threshold. Continued operation risks engine seizure."
            elif fault == "bearing":
                answer = f"I recommended {tier} because the vibration order tracking shows a massive shaft-speed spike, indicating impending bearing failure. High power settings will accelerate failure."
            else:
                answer = f"I recommended {tier} based on anomalous readings lowering the overall mission reliability score."
        else:
            answer = f"I am currently recommending {tier}, so a divert or RTB is not strictly necessary at this time."
    elif "wrong" in query or "status" in query or "health" in query:
        if fault == "normal":
            answer = f"The engine is operating nominally. EGT is {egt}°C and CHT is {cht}°C, both within expected bounds."
        else:
            answer = f"I am detecting an anomaly consistent with a '{fault}' condition. The current health index is {ctx.get('analytics', {}).get('health_index', 0)}%."
    else:
        answer = "I can explain our current mission tier recommendations or give a status report on engine health. Try asking 'why did you recommend divert?'"

    return {"answer": answer}


class PlannerRequest(BaseModel):
    altitude: float
    duration_hours: float
    throttle_pattern: str


@app.post("/api/planner")
def run_planner(req: PlannerRequest):
    sim_wear_rate = 1.5 if req.throttle_pattern == "aggressive" else 1.0

    current_wear = state.accumulated_wear_time
    theta_1 = 0.01
    theta_2 = 0.001

    final_wear = current_wear + (sim_wear_rate * req.duration_hours)

    final_hi_val = 1.0 - (theta_1 * math.exp(theta_2 * final_wear))
    final_health_index = max(0.0, final_hi_val * 100.0)

    try:
        t_end = math.log(1.0 / theta_1) / theta_2
        rul_effective = max(0.0, t_end - final_wear)
        final_rul_hours = rul_effective / sim_wear_rate
    except ValueError:
        final_rul_hours = 0.0

    is_safe = final_health_index >= 60.0

    return {
        "is_safe": is_safe,
        "final_health_index": round(final_health_index, 2),
        "final_rul_hours": round(final_rul_hours, 1),
        "message": f"Mission {'is SAFE' if is_safe else 'is UNSAFE'}. Expected final health index: {round(final_health_index, 1)}%."
    }


@app.get("/api/telemetry")
def get_telemetry(altitude: float = 10000, throttle: float = 100.0, fault_mode: str = "normal"):
    now = time.monotonic()
    if state.last_poll_s is None:
        state.last_poll_s = now
    dt = min(max(now - state.last_poll_s, 0.05), 5.0)
    state.last_poll_s = now
    state.sim_time_s += dt

    t_amb_c, density_ratio = calculate_isa(altitude)
    expected_metrics = calculate_expected(altitude, throttle)
    expected_rpm = expected_metrics["expected_rpm"]

    if fault_mode == "misfire":
        state.cumulative_wear += 0.5
        egt_target, cht_target = 60.0, 0.0
        kurt_target, op_target = 0.0, 0.0
        rpm_target, map_target = 220.0, 3.0
    elif fault_mode == "cooling":
        state.cumulative_wear += 0.3
        egt_target, cht_target = 0.0, 35.0
        kurt_target, op_target = 0.0, 12.0
        rpm_target, map_target = 0.0, 0.0
    elif fault_mode == "bearing":
        state.cumulative_wear += 0.4
        egt_target, cht_target = 0.0, 0.0
        kurt_target, op_target = 3.2, 0.0
        rpm_target, map_target = 0.0, 0.0
    else:
        state.cumulative_wear += 0.0005
        egt_target, cht_target = 0.0, 0.0
        kurt_target, op_target = 0.0, 0.0
        rpm_target, map_target = 0.0, 0.0

    state.egt_boost = ease(state.egt_boost, egt_target)
    state.cht_boost = ease(state.cht_boost, cht_target)
    state.kurt_boost = ease(state.kurt_boost, kurt_target)
    state.op_drop = ease(state.op_drop, op_target)
    state.rpm_penalty = ease(state.rpm_penalty, rpm_target)
    state.map_boost = ease(state.map_boost, map_target)

    state.load_wander = state.load_wander * 0.94 + random.uniform(-3.0, 3.0)
    state.kurt_wander = max(-0.05, min(0.05, state.kurt_wander * 0.9 + random.uniform(-0.008, 0.008)))

    rpm_now = expected_rpm - state.rpm_penalty + state.load_wander
    firing_rate = max(0.0, rpm_now / 120.0)

    state.crank_deg = (state.crank_deg + rpm_now * 6.0 * dt) % CYCLE_DEG
    for c in range(CYLINDERS):
        offset = CYCLE_DEG - FIRE_CRANK[c]
        wraps = math.floor((state.crank_deg + offset) / CYCLE_DEG)
        if wraps > state.fire_count[c]:
            state.fire_count[c] = wraps

    egt_decay = math.exp(-dt / TAU_EGT)
    cht_decay = math.exp(-dt / TAU_CHT)
    warmup = 1.0 - math.exp(-state.sim_time_s / CHT_WARMUP_T)

    for c in range(CYLINDERS):
        state.egt_wander[c] = max(-3.0, min(3.0, state.egt_wander[c] * 0.985 + random.uniform(-0.3, 0.3)))
        state.cht_wander[c] = max(-1.4, min(1.4, state.cht_wander[c] * 0.99 + random.uniform(-0.12, 0.12)))

        egt_target_c = 806.5 + firing_rate * 0.16 + CYL_TRIM_EGT[c] * warmup \
            + state.egt_wander[c] + state.load_wander * 0.010
        state.egt_state[c] = ease(state.egt_state[c], egt_target_c, 1.0 - egt_decay)

        cht_target_c = 91.0 + firing_rate * 0.05 + CYL_TRIM_CHT[c] + 2.2 * warmup \
            + state.cht_wander[c] + state.cht_boost
        state.cht_state[c] = ease(state.cht_state[c], cht_target_c, 1.0 - cht_decay)

    measured_egt = [e + random.uniform(-0.4, 0.4) for e in state.egt_state]
    measured_egt[0] += state.egt_boost
    measured_cht = [c + random.uniform(-0.3, 0.3) for c in state.cht_state]

    measured_map = 29.92 * density_ratio + state.map_boost + random.uniform(-0.1, 0.1)
    measured_op = 60.0 - state.op_drop + random.uniform(-0.4, 0.4)
    measured_ff = 8.5 * density_ratio * (rpm_now / expected_rpm) + random.uniform(-0.04, 0.04)
    measured_kurtosis = 2.9 + state.kurt_wander + state.kurt_boost + random.uniform(-0.02, 0.02)

    vibration_fft = [
        {"order": "0.5x", "amp": round(0.1 + random.uniform(0, 0.02), 2)},
        {"order": "1x", "amp": round(0.42 + firing_rate * 0.012 + random.uniform(-0.02, 0.02), 2)},
        {"order": "2x", "amp": round(0.3 + state.kurt_boost * 0.8 + random.uniform(0, 0.03), 2)},
        {"order": "3x", "amp": round(0.15 + firing_rate * 0.001 + random.uniform(0, 0.02), 2)},
    ]

    residuals = {
        "rpm": round(rpm_now - expected_metrics["expected_rpm"]),
        "egt": round(measured_egt[0] - expected_metrics["expected_egt"]),
        "cht": round(measured_cht[0] - expected_metrics["expected_cht"])
    }

    history_egt.append(measured_egt[0])
    if len(history_egt) > 30:
        history_egt.pop(0)

    z_score_val = 0
    if len(history_egt) == 30:
        mean_egt = sum(history_egt) / len(history_egt)
        variance = sum((x - mean_egt) ** 2 for x in history_egt) / len(history_egt)
        std_dev = math.sqrt(variance) if variance > 0 else 1
        z_score_val = abs(measured_egt[0] - mean_egt) / std_dev

    ml_anomaly_score, ml_anomaly_reason = detector.evaluate(residuals)

    egt_gap = measured_egt[0] - max(measured_egt[1:])
    is_anomaly = (ml_anomaly_score > 0.5) or (z_score_val > 3.0) or egt_gap > 4.0 or max(measured_cht) > 120.0 or measured_kurtosis > 5.0

    state.operating_hours += 1.0
    wear_rate = {
        "normal": 1.0,
        "misfire": 15.0,
        "cooling": 10.0,
        "bearing": 25.0
    }.get(fault_mode, 1.0)
    state.accumulated_wear_time += wear_rate

    theta_1 = 0.01
    theta_2 = 0.001
    t = state.accumulated_wear_time
    hi_val = max(0.0, 1.0 - (theta_1 * math.exp(theta_2 * t)))
    wear_health = hi_val
    
    # ==============================================================================
    # METHODOLOGICAL BASIS: AHP-Enhanced Composite Health Index
    # Reference: Jiang, Fan, Wen et al., "Health Status Assessment of Unmanned 
    # Aerial Vehicle Engine Based on AHP Enhancement and Multimodal Fusion," 
    # Computers, Materials & Continua, 2026.
    # 
    # AHP Weighting Rationale:
    # 1. Wear Formula (0.50) - Most direct representation of accumulated engine degradation.
    # 2. ML Anomaly Score (0.25) - High-level isolation forest screen for non-linear interactions.
    # 3. Physics Residuals (0.15) - Direct deviation from expected thermodynamic behavior.
    # 4. Vibration Kurtosis (0.10) - Specific mechanical/bearing wear indicator.
    # ==============================================================================
    anomaly_health = max(0.0, 1.0 - ml_anomaly_score)
    
    # Normalize physics residuals against expected noise
    res_mag = (abs(residuals["rpm"])/20.0 + abs(residuals["egt"])/10.0 + abs(residuals["cht"])/5.0) / 3.0
    physics_health = max(0.0, 1.0 - (res_mag / 2.0))
    
    kurt_dev = abs(measured_kurtosis - 2.9)
    vibration_health = max(0.0, 1.0 - (kurt_dev / 2.1))
    
    composite_hi_val = (
        0.50 * wear_health +
        0.25 * anomaly_health +
        0.15 * physics_health +
        0.10 * vibration_health
    )
    health_index = composite_hi_val * 100.0

    try:
        t_end = math.log(1.0 / theta_1) / theta_2
        rul_effective_time_remaining = max(0.0, t_end - t)
        rul_hours = rul_effective_time_remaining / wear_rate
    except ValueError:
        rul_hours = 0.0

    reliability_score = health_index / 100.0
    if reliability_score >= 0.95:
        tier = "CONTINUE"
    elif reliability_score >= 0.80:
        tier = "DERATE"
    elif reliability_score >= 0.60:
        tier = "DIVERT"
    else:
        tier = "RTB"

    suggested_action = None
    if tier in ["DIVERT", "RTB"]:
        if fault_mode == "misfire":
            suggested_action = "Cylinder misfire detected. Recommend immediate RTB to prevent total loss of thrust."
        elif fault_mode == "cooling":
            suggested_action = "Cooling degradation detected. Recommend divert to lower altitude to reduce thermal load."
        elif fault_mode == "bearing":
            suggested_action = "Bearing wear detected (high vibration). Recommend RTB, avoid high-vibration maneuvers."
        else:
            suggested_action = "Unknown anomaly detected. Recommend precautionary divert."

    alert_state = None
    if fault_mode == "misfire" and state.egt_boost > 4.0:
        alert_state = {"title": "SYS WARN: CYL-1 MISFIRE", "desc": f"Cyl-1 EGT {round(egt_gap, 1)}°C above bank average."}
    elif fault_mode == "cooling" and max(measured_cht) > 120.0:
        alert_state = {"title": "SYS CRIT: THERMAL LIMIT", "desc": "CHT baseline exceeded across all 4 cylinders."}
    elif fault_mode == "bearing" and measured_kurtosis > 5.0:
        alert_state = {"title": "SYS WARN: VIBRATION SPIKE", "desc": "Kurtosis > 5.0 at 2x Order frequency."}

    return {
        "timestamp": time.strftime("%H:%M:%S"),
        "hex_id": f"0x{random.randint(0, 16777215):06X}",
        "environment": {
            "altitude_ft": altitude,
            "throttle_pct": throttle,
            "ambient_temp_c": round(t_amb_c, 1),
            "air_density_ratio": round(density_ratio, 3),
            "confidence_status": detector.check_confidence(altitude, throttle)
        },
        "engine": {
            "rpm": round(rpm_now + random.uniform(-1, 1)),
            "map": round(measured_map, 1),
            "op": round(measured_op, 1),
            "ff": round(measured_ff, 1),
            "egt": [round(e, 1) for e in measured_egt],
            "cht": [round(c, 1) for c in measured_cht],
            "vibration_kurtosis": round(measured_kurtosis, 2)
        },
        "expected": {
            "rpm": round(expected_metrics["expected_rpm"]),
            "egt": round(expected_metrics["expected_egt"]),
            "cht": round(expected_metrics["expected_cht"])
        },
        "residuals": residuals,
        "vibration_fft": vibration_fft,
        "analytics": {
            "z_score": round(z_score_val, 2),
            "ml_anomaly_score": round(ml_anomaly_score, 3),
            "anomaly_reason": ml_anomaly_reason,
            "is_anomaly": is_anomaly,
            "health_index": round(health_index),
            "rul_hours": round(rul_hours),
            "mission_tier": tier,
            "suggested_action": suggested_action,
            "alert": alert_state
        }
    }


@app.post("/api/reset")
def reset_simulation():
    """Reinitialize the whole engine + wear state so a fresh evaluation
    always starts at 100% health."""
    global state
    state = EngineState()
    return {
        "ok": True,
        "message": "Engine simulation state reset",
        "health_index": 100.0,
    }