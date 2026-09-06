from fastapi import APIRouter
from state import EngineState
import state as state_module

router = APIRouter()

@router.post("/api/reset")
def reset_simulation():
    """Reinitialize the whole engine + wear state so a fresh evaluation
    always starts at 100% health."""
    state_module.state = EngineState()
    return {
        "ok":           True,
        "message":      "Engine simulation state reset",
        "health_index": 100.0,
    }
