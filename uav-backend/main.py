from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import telemetry, reset, history, tickets

app = FastAPI(title="MALE UAV Digital Twin API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
)

app.include_router(telemetry.router)
app.include_router(reset.router)
app.include_router(history.router)
app.include_router(tickets.router)