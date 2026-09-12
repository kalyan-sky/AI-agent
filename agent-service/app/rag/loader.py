"""Loads enterprise runbook documents: Markdown files with YAML frontmatter.

Frontmatter carries the metadata ingestion attaches to every chunk
(title, category, service, environment) so retrieval can filter on it.
"""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass
class Document:
    document_id: str
    title: str
    category: str
    service: str | None
    environment: str | None
    source: str
    text: str


def load_documents(directory: Path) -> list[Document]:
    documents = []
    for path in sorted(directory.glob("*.md")):
        frontmatter, body = _split_frontmatter(path.read_text(encoding="utf-8"))
        documents.append(
            Document(
                document_id=path.stem,
                title=frontmatter.get("title", path.stem),
                category=frontmatter.get("category", "general"),
                service=frontmatter.get("service"),
                environment=frontmatter.get("environment"),
                source=str(path),
                text=body.strip(),
            )
        )
    return documents


def _split_frontmatter(raw: str) -> tuple[dict, str]:
    if not raw.startswith("---"):
        return {}, raw
    _, frontmatter_raw, body = raw.split("---", 2)
    return yaml.safe_load(frontmatter_raw) or {}, body
