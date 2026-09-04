# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import math
import random
import time
from physics_model import calculate_isa, calculate_expected
from ml_model import detector

app = FastAPI(title="MALE UAV Digital Twin API")

# Allow Next.js frontend to talk to this Python server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
)

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

    # Calculate basic Health Index based on parameters
    health_index = 99
    if fault_mode != "normal":
        health_index -= random.uniform(20, 45)

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
            "health_index": round(health_index)
        }
    }