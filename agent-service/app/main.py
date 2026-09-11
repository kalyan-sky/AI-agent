"""FastAPI application entrypoint."""
import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request

from app.api.dependencies import get_or_create_request_id
from app.api.routes import router
from app.config import get_settings
from app.logging import configure_logging, get_logger

settings = get_settings()
configure_logging(settings.log_level)
logger = get_logger(settings.service_name)


@asynccontextmanager
async def lifespan(_app: FastAPI):
    logger.info("service_starting", environment=settings.environment)
    yield
    logger.info("service_stopping")


app = FastAPI(
    title="Enterprise AI Operations Agent Platform",
    description="AI-Ops Agent — investigates production incidents via RAG + tools + agent planning.",  # noqa: E501
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(router)


@app.middleware("http")
async def correlation_and_access_log(request: Request, call_next):
    request_id = get_or_create_request_id(request)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)

    response.headers["x-request-id"] = request_id
    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response
