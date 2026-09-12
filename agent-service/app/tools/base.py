"""Base tool interface.

Every tool the agent can call implements this contract: a name, a
description (rendered into the prompt's tool catalog), a Pydantic input
schema (the LLM's arguments are validated against this before execution
— never trusted as-is), a risk tier, and a timeout. Tools are the only
way the agent touches the outside world; there is no generic "run a
command" tool, and the executor (app/agent/executor.py) only ever calls
tools by name from an explicit allowlist built at startup — never
anything the LLM invents.
"""

from abc import ABC, abstractmethod
from typing import Any, Generic, TypeVar

from pydantic import BaseModel

from app.agent.policies import RiskTier

InputT = TypeVar("InputT", bound=BaseModel)


class ToolError(Exception):
    """Raised by a tool's run() on a handled failure (e.g. upstream 503).
    Tools should raise this (or let a real exception propagate) rather
    than silently swallowing an error and returning a fake success.
    """


class Tool(ABC, Generic[InputT]):
    name: str
    description: str
    input_schema: type[InputT]
    risk_tier: RiskTier
    timeout_s: float = 10.0

    @abstractmethod
    async def run(self, args: InputT) -> dict[str, Any]:
        """Execute the tool and return a JSON-serializable result dict."""
