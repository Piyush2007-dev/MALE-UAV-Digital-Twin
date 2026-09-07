from fastapi import APIRouter
from state import EngineState
import state as state_module
from api import telemetry as telemetry_module

router = APIRouter()

@router.post("/api/reset")
def reset_simulation():
    """Reinitialize the whole engine + wear state so a fresh evaluation
    always starts at 100% health."""
    state_module.state = EngineState()
    # Also clear the EGT history buffer so z-score anomaly detection resets
    telemetry_module.history_egt.clear()
    return {
        "ok":           True,
        "message":      "Engine simulation state reset",
        "health_index": 100.0,
    }
