"""Centralized, environment-driven configuration.

Every external dependency (LLM provider, embedding model, vector DB,
database, cache, downstream APIs) is configured here so that swapping a
provider or pointing at a different environment (local/dev/staging/prod)
is a pure configuration change — never a code change.
"""

from functools import lru_cache
from typing import Literal

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

    # Agent execution limits
    agent_max_iterations: int = 8
    agent_timeout_s: int = 90
    agent_min_confidence: float = 0.4

    # Failure injection (never true in prod)
    failure_injection_enabled: bool = False
    failure_injection_target: str = ""

    # GCP (informational; used by infra tooling, not runtime logic)
    gcp_project_id: str = ""
    gcp_region: str = "us-central1"


@lru_cache
def get_settings() -> Settings:
    return Settings()
