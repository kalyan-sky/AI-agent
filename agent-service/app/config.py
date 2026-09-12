"""Centralized, environment-driven configuration.

Every external dependency (LLM provider, embedding model, vector DB,
database, cache, downstream APIs) is configured here so that swapping a
provider or pointing at a different environment (local/dev/staging/prod)
is a pure configuration change — never a code change.
"""

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # General
    environment: Literal["local", "dev", "staging", "prod"] = "local"
    log_level: str = "INFO"
    service_name: str = "agent-service"

    # Agent API
    agent_api_host: str = "0.0.0.0"
    agent_api_port: int = 8000
    api_keys: str = ""  # "key1:role1,key2:role2"
    jwt_secret_key: str = "change-me-in-real-deployments"
    jwt_algorithm: str = "HS256"
    jwt_issuer: str = "ai-ops-agent"
    oauth_token_url: str = ""

    # LLM provider — primary + optional fallback (used only if the primary
    # fails after its own retries; see app/agent/graph.py). Cheapest-first
    # default: Claude Haiku 4.5 primary, empty fallback until you set one.
    llm_provider: Literal["anthropic", "openai", "gemini"] = "anthropic"
    llm_model: str = "claude-haiku-4-5"
    llm_fallback_provider: Literal["anthropic", "openai", "gemini", ""] = ""
    llm_fallback_model: str = ""
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    google_api_key: str = ""
    llm_request_timeout_s: int = 30
    llm_max_retries: int = 2

    # Embeddings
    embedding_provider: Literal["huggingface", "local-hash"] = "huggingface"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    embedding_dim: int = 384
    huggingface_api_token: str = ""

    # Vector DB
    qdrant_url: str = "http://qdrant:6333"
    qdrant_api_key: str = ""
    qdrant_collection: str = "enterprise_knowledge"
    qdrant_local_path: str = ""

    # RAG ingestion
    rag_chunk_size: int = 800
    rag_chunk_overlap: int = 100

    # Database
    database_url: str = "postgresql+asyncpg://aiops:change-me@postgres:5432/aiops"

    # Cache
    redis_url: str = "redis://redis:6379/0"

    # Mock enterprise API
    mock_enterprise_base_url: str = "http://mock-enterprise:9000"
    mock_enterprise_timeout_s: int = 10
    # Set only in the real GCP deployment (to mock-enterprise's Cloud Run
    # URL — see infrastructure/terraform/cloud_run.tf) so every call to it
    # carries a Cloud Run identity token; empty everywhere else (local
    # dev, tests, CI), where mock-enterprise has no auth of its own to
    # satisfy anyway.
    gcp_id_token_audience: str = ""

    # Agent execution limits
    agent_max_iterations: int = 8
    agent_timeout_s: int = 90
    agent_min_confidence: float = 0.4

    # Rate limiting (Redis-backed fixed window, keyed by API key — see
    # app/security/rate_limit.py) for the LLM/embedding-calling endpoints
    rate_limit_requests: int = 60
    rate_limit_window_s: int = 60

    # Failure injection (never true in prod)
    failure_injection_enabled: bool = False
    failure_injection_target: str = ""

    # GCP (informational; used by infra tooling, not runtime logic)
    gcp_project_id: str = ""
    gcp_region: str = "us-central1"

    @model_validator(mode="after")
    def _refuse_insecure_config_outside_local(self) -> "Settings":
        """Fail fast at startup rather than silently running dev/insecure
        config in a real environment — a wrong env var here should crash
        the process on boot, not surface as a mysterious auth failure or,
        worse, an unintentionally open endpoint in staging/prod."""
        if self.environment == "local":
            return self

        problems: list[str] = []
        if self.jwt_secret_key == "change-me-in-real-deployments":
            problems.append("JWT_SECRET_KEY is still the insecure default")
        if not self.api_keys.strip():
            problems.append("API_KEYS is empty")
        if "change-me" in self.database_url:
            problems.append("DATABASE_URL still contains the placeholder password")

        provider_key = {
            "anthropic": self.anthropic_api_key,
            "openai": self.openai_api_key,
            "gemini": self.google_api_key,
        }[self.llm_provider]
        if not provider_key:
            problems.append(f"LLM_PROVIDER is {self.llm_provider!r} but its API key is empty")

        if self.failure_injection_enabled:
            problems.append(
                "FAILURE_INJECTION_ENABLED must never be true outside environment=local"
            )

        if problems:
            raise ValueError(
                f"refusing to start in environment={self.environment!r} with insecure "
                f"config: {'; '.join(problems)}"
            )
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
