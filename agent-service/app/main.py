"""FastAPI application entrypoint."""

import time
from contextlib import asynccontextmanager

import structlog
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.dependencies import get_or_create_request_id
from app.api.routes import router
from app.config import get_settings
from app.logging import configure_logging, get_logger
from app.observability.metrics import http_request_duration_seconds, http_requests_total
from app.observability.tracing import configure_tracing

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
configure_tracing(settings, app)


@app.middleware("http")
async def correlation_and_access_log(request: Request, call_next):
    """Also the last line of defense against an unhandled exception: a
    handler registered via @app.exception_handler(Exception) looks like
    the obvious place for this, but Starlette special-cases a bare
    `Exception`/500 handler onto the *outermost* ServerErrorMiddleware —
    outside every middleware defined in this file (confirmed by running
    this: registering it that way silently dropped x-request-id and every
    security header from the resulting error response). Catching it here
    instead means the security_headers middleware below still wraps this
    response like any other, and the request still gets one access-log
    line and one metrics observation instead of neither.
    """
    request_id = get_or_create_request_id(request)
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id)

    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as exc:  # noqa: BLE001 - must never leak an internal error to the caller
        logger.error(
            "unhandled_exception",
            method=request.method,
            path=request.url.path,
            error=str(exc),
            exc_info=exc,
        )
        response = JSONResponse(status_code=500, content={"detail": "internal server error"})
    duration_s = time.perf_counter() - start

    response.headers["x-request-id"] = request_id

    route = request.scope.get("route")
    path_label = route.path if route is not None else request.url.path
    http_requests_total.labels(
        method=request.method, path=path_label, status_code=str(response.status_code)
    ).inc()
    http_request_duration_seconds.labels(method=request.method, path=path_label).observe(
        duration_s
    )

    logger.info(
        "http_request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=round(duration_s * 1000, 2),
    )
    return response


@app.middleware("http")
async def security_headers(request: Request, call_next):
    """This is a JSON-only API — no page is ever rendered here — so these
    are all safe to set unconditionally: nothing legitimately needs to
    frame this service, sniff its responses as another content type, or
    receive a referrer from it."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = "default-src 'none'"
    if settings.environment != "local":
        response.headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
    return response
