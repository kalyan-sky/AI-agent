"""Mock Enterprise API.

Full service catalog / incidents / seedable failure scenarios are
implemented in a later build phase. Tickets has a minimal working slice
(app/tickets.py) so agent-service's ticket proxy has something real to
call now.
"""
from fastapi import FastAPI

from app.tickets import router as tickets_router

app = FastAPI(title="Mock Enterprise API", version="0.1.0")
app.include_router(tickets_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "mock-enterprise"}
