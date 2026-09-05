from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import math
import random
import time
from isolation_forest import score_snapshot

app = FastAPI(title="MALE UAV Digital Twin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
)

# ---------------------------------------------------------------------------
# 4-cylinder, 4-stroke (Otto) cycle model
# ---------------------------------------------------------------------------
# A crankshaft turns 720° per full engine cycle; each cylinder fires once per
# cycle. With 4 cylinders in a 1-3-4-2 firing order the combustion events are
# spaced 180° of crank angle apart.  Per-cylinder exhaust-gas and cylinder-head
# temperatures are solved as first-order thermal lags driven by that cylinder's
# own firing rate, so the feed reads like a real engine instead of random noise.
# ---------------------------------------------------------------------------
CYLINDERS = 4
FIRING_ORDER = [0, 2, 3, 1]               # cylinders 1 -> 3 -> 4 -> 2
FIRE_CRANK = {c: 180.0 * i for i, c in enumerate(FIRING_ORDER)}
CYCLE_DEG = 720.0

# Static asymmetry between cylinders (sensor placement / injector trim).
# Real 4-cyl engines show a few °C bank-to-bank spread at cruise; without it
# the four traces pile onto one line.
CYL_TRIM_EGT = [2.0, -1.2, 0.5, -1.3]     # °C offset per cylinder at cruise
CYL_TRIM_CHT = [0.9, -0.7, 0.4, -0.6]

# Thermal response: exhaust gas reacts in seconds, the head in ~10 s
TAU_EGT = 1.0
TAU_CHT = 10.0
CHT_WARMUP_T = 45.0                        # coolant/head warm-up time constant (s)


class EngineState:
    """State carried between API calls: wear bookkeeping + engine-cycle state."""

    def __init__(self):
        # PHM bookkeeping
        self.cumulative_wear = 0.0

        # Smoothed fault envelopes (each eases toward its target per tick)
        self.egt_boost = 0.0    # Cyl 1 EGT during misfire
        self.cht_boost = 0.0    # All cylinders during cooling fault
        self.kurt_boost = 0.0   # Bearing fault kurtosis
        self.op_drop = 0.0      # Oil pressure drop during cooling fault
        self.rpm_penalty = 0.0  # RPM sag during misfire
        self.map_boost = 0.0    # MAP rise during misfire

        # Crankshaft & thermal state
        self.sim_time_s = 0.0                 # simulated engine running time
        self.last_poll_s = None               # wall clock of previous poll
        self.crank_deg = random.uniform(0.0, CYCLE_DEG)
        self.fire_count = [0, 0, 0, 0]        # total firings per cylinder
        self.egt_state = [806.0, 806.0, 806.0, 806.0]
        self.cht_state = [91.0, 91.0, 91.0, 91.0]
        # Slow cylinder-to-cylinder drift.  Seeded apart so the traces are
        # visibly separated and alive from the first poll (no 2-min warm-in).
        self.egt_wander = [random.uniform(-1.6, 1.6) for _ in range(CYLINDERS)]
        self.cht_wander = [random.uniform(-0.9, 0.9) for _ in range(CYLINDERS)]
        self.load_wander = 0.0                # cruise/throttle corrections
        self.kurt_wander = 0.0


state = EngineState()


def ease(current: float, target: float, rate: float = 0.18) -> float:
    """Move one step toward target (first-order filter)."""
    return current + (target - current) * rate


def calculate_isa(altitude_ft: float):
    """ISA model for altitude physics."""
    altitude_m = altitude_ft * 0.3048
    T0 = 288.15  # Sea level standard temp (K)
    L = 0.0065   # Lapse rate (K/m)

    T_amb_k = T0 - (L * altitude_m)
    T_amb_c = T_amb_k - 273.15
    density_ratio = math.pow((T_amb_k / T0), 4.256)

    return T_amb_c, density_ratio


@app.get("/api/telemetry")
def get_telemetry(altitude: float = 10000, fault_mode: str = "normal"):
    now = time.monotonic()
    if state.last_poll_s is None:
        state.last_poll_s = now
    dt = min(max(now - state.last_poll_s, 0.05), 5.0)
    state.last_poll_s = now
    state.sim_time_s += dt

    t_amb_c, density_ratio = calculate_isa(altitude)
    expected_rpm = 4800 * density_ratio   # lower air density at altitude -> less power

    # --- Fault envelopes: what each injection drives the engine toward
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
        # Nominal: only an imperceptible long-term drift (~55 h at 1 Hz).
        state.cumulative_wear += 0.0005
        egt_target, cht_target = 0.0, 0.0
        kurt_target, op_target = 0.0, 0.0
        rpm_target, map_target = 0.0, 0.0

    # Ramp fault effects instead of applying them as hard steps
    state.egt_boost = ease(state.egt_boost, egt_target)
    state.cht_boost = ease(state.cht_boost, cht_target)
    state.kurt_boost = ease(state.kurt_boost, kurt_target)
    state.op_drop = ease(state.op_drop, op_target)
    state.rpm_penalty = ease(state.rpm_penalty, rpm_target)
    state.map_boost = ease(state.map_boost, map_target)

    # Cruise "governor" wander: small smooth corrections around the setpoint
    state.load_wander = state.load_wander * 0.94 + random.uniform(-3.0, 3.0)
    state.kurt_wander = max(-0.05, min(0.05, state.kurt_wander * 0.9 + random.uniform(-0.008, 0.008)))

    rpm_now = expected_rpm - state.rpm_penalty + state.load_wander
    firing_rate = max(0.0, rpm_now / 120.0)   # each cylinder fires once per 2 revolutions

    # --- Advance the crankshaft and count each cylinder's combustion events
    state.crank_deg = (state.crank_deg + rpm_now * 6.0 * dt) % CYCLE_DEG
    for c in range(CYLINDERS):
        offset = CYCLE_DEG - FIRE_CRANK[c]
        wraps = math.floor((state.crank_deg + offset) / CYCLE_DEG)
        if wraps > state.fire_count[c]:
            state.fire_count[c] = wraps

    # --- Thermal model -------------------------------------------------------
    # Each cylinder's EGT/CHT relax toward an equilibrium set by its own firing
    # rate (combustion heat) and cylinder trim, so the four traces stay gently
    # separated, drift slowly, and move together when load/RPM change.
    egt_decay = math.exp(-dt / TAU_EGT)
    cht_decay = math.exp(-dt / TAU_CHT)
    warmup = 1.0 - math.exp(-state.sim_time_s / CHT_WARMUP_T)   # cold-start climb

    for c in range(CYLINDERS):
        # Mean-reverting random walk: EGT drifts ±2-3 °C over ~a minute,
        # CHT ±~1 °C.  Step sizes are small enough to stay smooth tick-to-tick
        # but large enough that the traces never freeze on one integer.
        state.egt_wander[c] = max(-3.0, min(3.0, state.egt_wander[c] * 0.985 + random.uniform(-0.3, 0.3)))
        state.cht_wander[c] = max(-1.4, min(1.4, state.cht_wander[c] * 0.99 + random.uniform(-0.12, 0.12)))

        egt_target_c = 806.5 + firing_rate * 0.16 + CYL_TRIM_EGT[c] * warmup \
            + state.egt_wander[c] + state.load_wander * 0.010
        state.egt_state[c] = ease(state.egt_state[c], egt_target_c, 1.0 - egt_decay)

        cht_target_c = 91.0 + firing_rate * 0.05 + CYL_TRIM_CHT[c] + 2.2 * warmup \
            + state.cht_wander[c] + state.cht_boost
        state.cht_state[c] = ease(state.cht_state[c], cht_target_c, 1.0 - cht_decay)

    # Sensor noise: EGT probes read ±0.4 °C, CHT ±0.3 °C
    measured_egt = [e + random.uniform(-0.4, 0.4) for e in state.egt_state]
    measured_egt[0] += state.egt_boost          # misfire: unburnt fuel burns in the exhaust
    measured_cht = [c + random.uniform(-0.3, 0.3) for c in state.cht_state]

    # Manifold / oil / fuel / vibration
    measured_map = 29.92 * density_ratio + state.map_boost + random.uniform(-0.1, 0.1)
    measured_op = 60.0 - state.op_drop + random.uniform(-0.4, 0.4)
    measured_ff = 8.5 * density_ratio * (rpm_now / expected_rpm) + random.uniform(-0.04, 0.04)
    measured_kurtosis = 2.9 + state.kurt_wander + state.kurt_boost + random.uniform(-0.02, 0.02)

    # Order-tracked vibration: 1x tracks firing rate, 2x follows bearing wear
    vibration_fft = [
        {"order": "0.5x", "amp": round(0.1 + random.uniform(0, 0.02), 2)},
        {"order": "1x", "amp": round(0.42 + firing_rate * 0.012 + random.uniform(-0.02, 0.02), 2)},
        {"order": "2x", "amp": round(0.3 + state.kurt_boost * 0.8 + random.uniform(0, 0.03), 2)},
        {"order": "3x", "amp": round(0.15 + firing_rate * 0.001 + random.uniform(0, 0.02), 2)},
    ]

    # Fault signatures on the eased traces (real thresholds, not z-scores,
    # which cannot separate a smooth fault ramp from sensor jitter):
    #   misfire -> cyl-1 EGT isolated above the other three cylinders
    #   cooling -> absolute CHT over-temperature
    #   bearing -> kurtosis above the 2x-order warning level
    egt_gap = measured_egt[0] - max(measured_egt[1:])
    is_anomaly = egt_gap > 4.0 or max(measured_cht) > 120.0 or measured_kurtosis > 5.0

    health_index = max(0.0, 100.0 - state.cumulative_wear)
    rul_hours = max(0, int((health_index / 100.0) * 2000))

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
        "environment": {"altitude_ft": altitude},
        "engine": {
            "rpm": round(rpm_now + random.uniform(-1, 1)),
            "map": round(measured_map, 1),
            "op": round(measured_op, 1),
            "ff": round(measured_ff, 1),
            "egt": [round(e, 1) for e in measured_egt],
            "cht": [round(c, 1) for c in measured_cht],
            "vibration_kurtosis": round(measured_kurtosis, 2)
        },
        "vibration_fft": vibration_fft,
        "analytics": {
            "is_anomaly": is_anomaly,
            "isolation_forest": score_snapshot({
                "rpm": rpm_now, "map": measured_map,
                "op": measured_op, "ff": measured_ff,
                "egt": measured_egt, "cht": measured_cht,
                "vibration_kurtosis": measured_kurtosis,
                "altitude_ft": altitude,
            }),
            "health_index": round(health_index, 2),
            "rul_hours": rul_hours,
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
