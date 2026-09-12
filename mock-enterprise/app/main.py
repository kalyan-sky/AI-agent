"""Mock Enterprise API.

Simulates the internal systems a real incident-investigation agent would
call: service health/deployment/logs (app/services_catalog.py), tickets
(app/tickets.py), incidents (app/incidents.py), and seedable per-service
failure scenarios (app/scenarios.py, controlled via app/admin.py) so demos
can walk through healthy / failed-deployment / db-outage / etc. states.
"""
from fastapi import FastAPI

from app.admin import router as admin_router
from app.incidents import router as incidents_router
from app.services_catalog import router as services_router
from app.tickets import router as tickets_router

app = FastAPI(title="Mock Enterprise API", version="0.1.0")
app.include_router(tickets_router)
app.include_router(services_router)
app.include_router(incidents_router)
app.include_router(admin_router)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "mock-enterprise"}
