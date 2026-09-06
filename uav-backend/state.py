import random
from constants import (
    CYLINDERS, CYCLE_DEG,
    BASELINE_EGT, BASELINE_CHT
)

class EngineState:
    """State carried between API calls: wear bookkeeping + engine-cycle state."""
    
    def __init__(self):
        self.cumulative_wear = 0.0
        self.operating_hours = 0.0         # Accumulated time in real hours (dt / 3600)
        self.accumulated_wear_time = 0.0   # Wear severity scaled by dt

        self.egt_boost   = 0.0
        self.cht_boost   = 0.0
        self.kurt_boost  = 0.0
        self.op_drop     = 0.0
        self.rpm_penalty = 0.0
        self.map_boost   = 0.0

        self.sim_time_s  = 0.0
        self.last_poll_s = None
        self.crank_deg   = random.uniform(0.0, CYCLE_DEG)
        self.fire_count  = [0, 0, 0, 0]
        self.egt_state   = [BASELINE_EGT for _ in range(CYLINDERS)]
        self.cht_state   = [BASELINE_CHT for _ in range(CYLINDERS)]
        self.egt_wander  = [random.uniform(-1.6, 1.6) for _ in range(CYLINDERS)]
        self.cht_wander  = [random.uniform(-0.9, 0.9) for _ in range(CYLINDERS)]
        self.load_wander = 0.0
        self.kurt_wander = 0.0

state = EngineState()
