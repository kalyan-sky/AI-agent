"""search_knowledge tool — wraps the RAG retriever."""

from pydantic import BaseModel, Field

from app.agent.policies import RiskTier
from app.api.schemas import RagSearchRequest
from app.config import Settings
from app.services import rag_service
from app.tools.base import Tool


class SearchKnowledgeInput(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000)
    top_k: int = Field(default=3, ge=1, le=10)
    service: str | None = None


class SearchKnowledgeTool(Tool[SearchKnowledgeInput]):
    name = "search_knowledge"
    description = (
        "Search enterprise runbooks for troubleshooting guidance relevant to a query. "
        "Use this before guessing a root cause."
    )
    input_schema = SearchKnowledgeInput
    risk_tier = RiskTier.READ_ONLY
    timeout_s = 10.0

    def __init__(self, settings: Settings):
        self._settings = settings

    async def run(self, args: SearchKnowledgeInput) -> dict:
        response = await rag_service.search(
            RagSearchRequest(query=args.query, top_k=args.top_k, service=args.service),
            self._settings,
        )
        return {
            "results": [
                {
                    "document_id": r.document_id,
                    "title": r.title,
                    "text": r.text,
                    "score": r.score,
                }
                for r in response.results
            ]
        }
