from fastapi import APIRouter

router = APIRouter()

@router.get("/api/tickets")
def get_tickets():
    """Placeholder for maintenance tickets endpoint."""
    return {"tickets": []}
