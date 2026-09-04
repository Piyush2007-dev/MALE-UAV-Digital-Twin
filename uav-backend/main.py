# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import math
import random
import time
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from physics_model import calculate_isa, calculate_expected
from ml_model import detector

app = FastAPI(title="MALE UAV Digital Twin API")

# Allow Next.js frontend to talk to this Python server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
)

class DigitalTwinState:
    def __init__(self):
        self.operating_hours = 0.0
        self.accumulated_wear_time = 0.0
        
    def reset(self):
        self.operating_hours = 0.0
        self.accumulated_wear_time = 0.0

state = DigitalTwinState()

@app.post("/api/reset")
def reset_simulation():
    state.reset()
    return {"status": "reset_successful"}

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

# Statistical history for Z-Score Anomaly Detection
history_egt = []

@app.get("/api/telemetry")
def get_telemetry(altitude: float = 10000, throttle: float = 100.0, fault_mode: str = "normal"):
    """
    Generates 1 tick of engine telemetry using Python logic and physics.
    """
    global history_egt
    
    # 1. Apply Physics (ISA Model & Expected values)
    t_amb_c, density_ratio = calculate_isa(altitude)
    expected_metrics = calculate_expected(altitude, throttle)
    
    # Base Engine Parameters driven by throttle and altitude
    base_rpm = expected_metrics["expected_rpm"]
    cht_base = expected_metrics["expected_cht"]
    egt_base = expected_metrics["expected_egt"]
    
    # 2. Generate Sensor Data
    rpm = base_rpm + random.uniform(-15, 15)
    egt = [egt_base + random.uniform(-5, 5) for _ in range(4)]
    cht = [cht_base + random.uniform(-2, 2) for _ in range(4)]
    kurtosis = 2.9 + random.uniform(-0.1, 0.1)

    # 3. Fault Injection Logic
    if fault_mode == "misfire":
        egt[0] += random.uniform(100, 130)  # Massive spike in Cyl 1
        rpm -= random.uniform(150, 300)     # Engine stumbles
    elif fault_mode == "cooling":
        cht = [c + random.uniform(25, 35) for c in cht] # All CHTs rise
    elif fault_mode == "bearing":
        kurtosis += random.uniform(2.5, 3.5) # Vibration spike

    # Calculate Residuals (Actual - Expected)
    residuals = {
        "rpm": round(rpm - expected_metrics["expected_rpm"]),
        "egt": round(egt[0] - expected_metrics["expected_egt"]),
        "cht": round(cht[0] - expected_metrics["expected_cht"])
    }

    # 4. Actual Python Analytics: Z-Score Statistical Anomaly Detection + ML Model
    # Formula B8 from the SIH26054 report
    history_egt.append(egt[0])
    if len(history_egt) > 30:
        history_egt.pop(0)
    
    z_score_val = 0
    if len(history_egt) == 30:
        mean_egt = sum(history_egt) / len(history_egt)
        variance = sum((x - mean_egt) ** 2 for x in history_egt) / len(history_egt)
        std_dev = math.sqrt(variance) if variance > 0 else 1
        
        # Calculate Z-Score of current EGT
        z_score_val = abs(egt[0] - mean_egt) / std_dev

    # Evaluate residuals through the Isolation Forest model
    ml_anomaly_score, ml_anomaly_reason = detector.evaluate(residuals)
    
    # Trigger anomaly if either model flags it
    is_anomaly = (ml_anomaly_score > 0.5) or (z_score_val > 3.0)

    # 5. Real RUL Estimation (Exponential Wear Trajectory)
    state.operating_hours += 1.0 # Simulate 1 hour per tick
    
    wear_rate = {
        "normal": 1.0,
        "misfire": 15.0,
        "cooling": 10.0,
        "bearing": 25.0
    }.get(fault_mode, 1.0)
    
    state.accumulated_wear_time += wear_rate
    
    theta_1 = 0.01
    theta_2 = 0.001
    
    # HI(t) = 1 - θ1 * exp(θ2 * t)
    t = state.accumulated_wear_time
    hi_val = 1.0 - (theta_1 * math.exp(theta_2 * t))
    hi_val = max(0.0, hi_val)
    health_index = hi_val * 100.0
    
    # RUL Calculation from fitted trajectory
    try:
        t_end = math.log(1.0 / theta_1) / theta_2
        rul_effective_time_remaining = max(0.0, t_end - t)
        rul_hours = rul_effective_time_remaining / wear_rate
    except ValueError:
        rul_hours = 0.0

    # Phase 4: Mission Reliability Tier
    reliability_score = (health_index / 100.0) * (1.0 - ml_anomaly_score * 0.5)
    if reliability_score >= 0.95:
        tier = "CONTINUE"
    elif reliability_score >= 0.80:
        tier = "DERATE"
    elif reliability_score >= 0.60:
        tier = "DIVERT"
    else:
        tier = "RTB"

    # Phase 5: Health-Aware Reroute Suggestion
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

    return {
        "timestamp": time.strftime("%H:%M:%S"),
        "environment": {
            "altitude_ft": altitude,
            "throttle_pct": throttle,
            "ambient_temp_c": round(t_amb_c, 1),
            "air_density_ratio": round(density_ratio, 3)
        },
        "engine": {
            "rpm": round(rpm),
            "egt": [round(e) for e in egt],
            "cht": [round(c) for c in cht],
            "vibration_kurtosis": round(kurtosis, 2)
        },
        "expected": {
            "rpm": round(expected_metrics["expected_rpm"]),
            "egt": round(expected_metrics["expected_egt"]),
            "cht": round(expected_metrics["expected_cht"])
        },
        "residuals": residuals,
        "analytics": {
            "z_score": round(z_score_val, 2),
            "ml_anomaly_score": round(ml_anomaly_score, 3),
            "anomaly_reason": ml_anomaly_reason,
            "is_anomaly": is_anomaly,
            "health_index": round(health_index),
            "rul_hours": round(rul_hours),
            "mission_tier": tier,
            "suggested_action": suggested_action
        }
    }