"""Runtime failure injection — deliberately breaking one named dependency
in an otherwise-running service, to demonstrate this project's graceful-
degradation paths live rather than only in pytest.

Controlled by two Settings fields (FAILURE_INJECTION_ENABLED,
FAILURE_INJECTION_TARGET) that default to off/empty and, per
Settings._refuse_insecure_config_outside_local, can never be turned on
outside environment="local" — a wrong env var here must never let this
ship active in staging/prod.

Targets, each checked at the one real call site that would fail this way
for real (`grep -rn "should_inject" app/` finds all four):
  - llm_timeout       app/agent/llm_provider.py (build_llm)
  - qdrant_down       app/rag/qdrant.py (get_client)
  - postgres_down     app/database/session.py (get_session_factory)
  - enterprise_500 /
    enterprise_timeout app/tools/http.py (get/post/patch)
"""

from app.config import Settings


def should_inject(settings: Settings, target: str) -> bool:
    return settings.failure_injection_enabled and settings.failure_injection_target == target
