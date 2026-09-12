"""LLM provider abstraction.

Deliberately a plain text-completion interface — `complete(system,
messages) -> str` — with no vendor-specific tool-calling schema. The
agent graph (app/agent/graph.py) implements its own ReAct-style loop:
tools are described as text in the prompt (app/agent/prompts.py), the
LLM's response is parsed as structured JSON to decide the next action,
and the executor validates/runs the tool itself. This keeps every
provider interchangeable — swapping ANTHROPIC/OPENAI/GEMINI is a config
change, never a code change — and avoids depending on any one vendor's
native tool-use/tool-result message contract, which differs enough
between providers (and is strict enough about pairing) that supporting
it natively for three vendors would be its own project.

Two providers are configured: `LLM_PROVIDER` (primary) and
`LLM_FALLBACK_PROVIDER` (used only if the primary fails after its own
retries — see graph.py's `call_llm_with_fallback`).
"""

import json
from dataclasses import dataclass
from typing import Any, Protocol, cast

import httpx
import structlog

from app.config import Settings

logger = structlog.get_logger(__name__)


class LLMTransientError(Exception):
    """Retryable: rate limit, timeout, 5xx, connection error."""


class LLMFatalError(Exception):
    """Not retryable: bad request, auth failure, invalid model."""


@dataclass
class LLMMessage:
    role: str  # "user" | "assistant"
    content: str


class LLMProvider(Protocol):
    async def complete(self, system: str, messages: list[LLMMessage]) -> str: ...


class AnthropicProvider:
    def __init__(self, model: str, api_key: str, timeout_s: int):
        import anthropic

        self._client = anthropic.AsyncAnthropic(api_key=api_key or None, timeout=timeout_s)
        self._model = model

    async def complete(self, system: str, messages: list[LLMMessage]) -> str:
        import anthropic

        try:
            response = await self._client.messages.create(
                model=self._model,
                max_tokens=2048,
                system=system,
                messages=cast(Any, [{"role": m.role, "content": m.content} for m in messages]),
            )
        except anthropic.RateLimitError as exc:
            raise LLMTransientError(f"anthropic rate limited: {exc}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMTransientError(f"anthropic connection error: {exc}") from exc
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMTransientError(f"anthropic server error: {exc}") from exc
            raise LLMFatalError(f"anthropic request error: {exc}") from exc

        return "".join(block.text for block in response.content if block.type == "text")


class OpenAIProvider:
    """Also serves OpenRouter and any other OpenAI-compatible endpoint —
    just point `OPENAI_BASE_URL` at it (e.g. https://openrouter.ai/api/v1).
    """

    def __init__(self, model: str, api_key: str, base_url: str, timeout_s: int):
        from openai import AsyncOpenAI

        self._client = AsyncOpenAI(
            api_key=api_key or None, base_url=base_url or None, timeout=timeout_s
        )
        self._model = model

    async def complete(self, system: str, messages: list[LLMMessage]) -> str:
        import openai

        oa_messages = [{"role": "system", "content": system}] + [
            {"role": m.role, "content": m.content} for m in messages
        ]
        try:
            response = await self._client.chat.completions.create(
                model=self._model, messages=cast(Any, oa_messages), max_tokens=2048
            )
        except openai.RateLimitError as exc:
            raise LLMTransientError(f"openai rate limited: {exc}") from exc
        except openai.APIConnectionError as exc:
            raise LLMTransientError(f"openai connection error: {exc}") from exc
        except openai.APIStatusError as exc:
            if exc.status_code >= 500:
                raise LLMTransientError(f"openai server error: {exc}") from exc
            raise LLMFatalError(f"openai request error: {exc}") from exc

        return response.choices[0].message.content or ""


class GeminiProvider:
    """REST-based (no google SDK dependency). The request/response shape
    below follows Gemini's long-stable `generateContent` contract; this
    project could not reach ai.google.dev from its dev sandbox to verify
    it's still current at time of writing — confirm against
    https://ai.google.dev/api/generate-content before relying on it in
    a new environment.
    """

    def __init__(self, model: str, api_key: str, timeout_s: int):
        self._model = model
        self._api_key = api_key
        self._timeout_s = timeout_s

    async def complete(self, system: str, messages: list[LLMMessage]) -> str:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self._model}:generateContent?key={self._api_key}"
        )
        payload = {
            "system_instruction": {"parts": [{"text": system}]},
            "contents": [
                {
                    "role": "model" if m.role == "assistant" else "user",
                    "parts": [{"text": m.content}],
                }
                for m in messages
            ],
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout_s) as client:
                resp = await client.post(url, json=payload)
        except httpx.TimeoutException as exc:
            raise LLMTransientError(f"gemini timeout: {exc}") from exc
        except httpx.TransportError as exc:
            raise LLMTransientError(f"gemini connection error: {exc}") from exc

        if resp.status_code == 429 or resp.status_code >= 500:
            raise LLMTransientError(f"gemini error {resp.status_code}: {resp.text}")
        if resp.status_code >= 400:
            raise LLMFatalError(f"gemini error {resp.status_code}: {resp.text}")

        data = resp.json()
        try:
            return "".join(
                part.get("text", "") for part in data["candidates"][0]["content"]["parts"]
            )
        except (KeyError, IndexError) as exc:
            raise LLMFatalError(
                f"unexpected gemini response shape: {json.dumps(data)[:500]}"
            ) from exc


class FallbackLLM:
    """Wraps a primary + optional fallback provider behind the same
    `LLMProvider` interface, so callers (planner.py) never need to know
    a fallback exists.
    """

    def __init__(self, primary: LLMProvider, fallback: LLMProvider | None):
        self._primary = primary
        self._fallback = fallback

    async def complete(self, system: str, messages: list[LLMMessage]) -> str:
        try:
            return await self._primary.complete(system, messages)
        except LLMTransientError as exc:
            if self._fallback is None:
                raise
            logger.warning("llm_primary_failed_using_fallback", error=str(exc))
            return await self._fallback.complete(system, messages)


def build_llm(settings: Settings) -> LLMProvider:
    primary = build_provider(settings.llm_provider, settings.llm_model, settings)
    fallback = None
    if settings.llm_fallback_provider:
        fallback_model = settings.llm_fallback_model or settings.llm_model
        fallback = build_provider(settings.llm_fallback_provider, fallback_model, settings)
    return FallbackLLM(primary, fallback)


def build_provider(provider_name: str, model: str, settings: Settings) -> LLMProvider:
    if provider_name == "anthropic":
        return AnthropicProvider(model, settings.anthropic_api_key, settings.llm_request_timeout_s)
    if provider_name == "openai":
        return OpenAIProvider(
            model, settings.openai_api_key, settings.openai_base_url, settings.llm_request_timeout_s
        )
    if provider_name == "gemini":
        return GeminiProvider(model, settings.google_api_key, settings.llm_request_timeout_s)
    raise ValueError(f"unknown LLM provider: {provider_name!r}")
