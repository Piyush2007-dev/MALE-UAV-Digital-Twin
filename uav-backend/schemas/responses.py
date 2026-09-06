from pydantic import BaseModel
from typing import List, Dict, Any, Optional

class TelemetryResponse(BaseModel):
    timestamp: str
    hex_id: str
    environment: Dict[str, Any]
    engine: Dict[str, Any]
    expected: Dict[str, Any]
    residuals: Dict[str, Any]
    vibration_fft: List[Dict[str, Any]]
    analytics: Dict[str, Any]
