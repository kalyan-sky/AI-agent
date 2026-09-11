"""Mock Enterprise API — placeholder entrypoint.

Full service catalog / tickets / incidents endpoints are implemented in
Phase 3. For Phase 1 this exposes only the health endpoint so it can
participate in the docker-compose dependency graph and be health-checked.
"""
from fastapi import FastAPI

app = FastAPI(title="Mock Enterprise API", version="0.1.0")


@app.get("/health")
async def health() -> dict:
    return {"status": "ok", "service": "mock-enterprise"}
