# main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import math
import random
import time

app = FastAPI(title="MALE UAV Digital Twin API")

# Allow Next.js frontend to talk to this Python server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
)

# Statistical history for Z-Score Anomaly Detection
history_egt = []

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

@app.get("/api/telemetry")
def get_telemetry(altitude: float = 10000, fault_mode: str = "normal"):
    """
    Generates 1 tick of engine telemetry using Python logic and physics.
    """
    global history_egt
    
    # 1. Apply Physics (ISA Model)
    t_amb_c, density_ratio = calculate_isa(altitude)
    
    # Base Engine Parameters adjusted for thin air
    base_rpm = 4800 * density_ratio
    cht_base = 95 + (t_amb_c * 0.5)
    
    # 2. Generate Sensor Data
    rpm = base_rpm + random.uniform(-15, 15)
    egt = [810 + random.uniform(-5, 5) for _ in range(4)]
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

    # 4. Actual Python Analytics: Z-Score Statistical Anomaly Detection
    # Formula B8 from the SIH26054 report
    history_egt.append(egt[0])
    if len(history_egt) > 30:
        history_egt.pop(0)
    
    anomaly_score = 0
    if len(history_egt) == 30:
        mean_egt = sum(history_egt) / len(history_egt)
        variance = sum((x - mean_egt) ** 2 for x in history_egt) / len(history_egt)
        std_dev = math.sqrt(variance) if variance > 0 else 1
        
        # Calculate Z-Score of current EGT
        z_score = abs(egt[0] - mean_egt) / std_dev
        
        # If Z-score > 3, statistically significant anomaly
        if z_score > 3.0:
            anomaly_score = z_score

    # Calculate basic Health Index based on parameters
    health_index = 99
    if fault_mode != "normal":
        health_index -= random.uniform(20, 45)

    return {
        "timestamp": time.strftime("%H:%M:%S"),
        "environment": {
            "altitude_ft": altitude,
            "ambient_temp_c": round(t_amb_c, 1),
            "air_density_ratio": round(density_ratio, 3)
        },
        "engine": {
            "rpm": round(rpm),
            "egt": [round(e) for e in egt],
            "cht": [round(c) for c in cht],
            "vibration_kurtosis": round(kurtosis, 2)
        },
        "analytics": {
            "z_score": round(anomaly_score, 2),
            "is_anomaly": anomaly_score > 3.0,
            "health_index": round(health_index)
        }
    }