"""Fail-fast config validation: insecure defaults are fine for local dev
but must refuse to boot the process in a real environment, rather than
surfacing later as a confusing auth failure or a silently-open endpoint.
"""

import pytest
from pydantic import ValidationError

from app.config import Settings


def _base_secure_kwargs(**overrides) -> dict:
    kwargs = {
        "environment": "staging",
        "jwt_secret_key": "a-real-secret-not-the-default",
        "api_keys": "real-key:viewer",
        "database_url": "postgresql+asyncpg://aiops:s3cr3t@10.0.0.5:5432/aiops",
        "llm_provider": "anthropic",
        "anthropic_api_key": "sk-ant-real-key",
    }
    kwargs.update(overrides)
    return kwargs


def test_local_environment_allows_all_defaults():
    # No overrides at all — the class defaults (empty api_keys, the
    # placeholder jwt secret, etc.) must stay usable for local dev.
    Settings(_env_file=None, environment="local")


def test_staging_with_secure_config_boots_fine():
    Settings(_env_file=None, **_base_secure_kwargs())


@pytest.mark.parametrize(
    "override",
    [
        {"jwt_secret_key": "change-me-in-real-deployments"},
        {"api_keys": ""},
        {"api_keys": "   "},
        {"database_url": "postgresql+asyncpg://aiops:change-me@10.0.0.5:5432/aiops"},
        {"anthropic_api_key": ""},
        {"failure_injection_enabled": True, "failure_injection_target": "llm_timeout"},
    ],
)
def test_staging_refuses_to_boot_with_insecure_config(override):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **_base_secure_kwargs(**override))


def test_error_names_every_problem_at_once():
    with pytest.raises(ValidationError) as exc_info:
        Settings(
            _env_file=None,
            **_base_secure_kwargs(jwt_secret_key="change-me-in-real-deployments", api_keys=""),
        )
    message = str(exc_info.value)
    assert "JWT_SECRET_KEY" in message
    assert "API_KEYS" in message
