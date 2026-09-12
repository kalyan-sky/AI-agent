"""Structured JSON logging.

Every log line is a JSON object carrying whatever contextvars are bound
(request_id, conversation_id, execution_id, ...) plus the event and level.
Never bind or log secrets, API keys, tokens, or passwords — see
`SENSITIVE_KEYS` which is scrubbed defensively before emission.
"""

import logging
import sys
from typing import Any

import structlog
from structlog.types import EventDict, WrappedLogger

SENSITIVE_KEYS = {
    "api_key",
    "authorization",
    "password",
    "token",
    "access_token",
    "secret",
    "jwt",
}


def _scrub_sensitive(_logger: WrappedLogger, _method_name: str, event_dict: EventDict) -> Any:
    for key in list(event_dict.keys()):
        if key.lower() in SENSITIVE_KEYS:
            event_dict[key] = "***redacted***"
    return event_dict


def configure_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper(), logging.INFO),
    )

    structlog.configure(
        processors=[
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso"),
            _scrub_sensitive,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(
            getattr(logging, level.upper(), logging.INFO)
        ),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )


def get_logger(name: str = "agent-service") -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)
