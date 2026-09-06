from fastapi import APIRouter

router = APIRouter()

@router.get("/api/history")
def get_history():
    """Placeholder for mission replay history endpoint."""
    return {"history": []}
