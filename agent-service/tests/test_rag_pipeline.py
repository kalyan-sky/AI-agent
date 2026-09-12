"""Unit tests for the chunker and loader — the parts of the ingestion
pipeline that don't need a running Qdrant or an embedding model.
"""

from pathlib import Path

import pytest

from app.rag.chunker import chunk_text
from app.rag.loader import load_documents


def test_chunk_text_keeps_short_paragraphs_together():
    text = "para one.\n\npara two.\n\npara three."
    chunks = chunk_text("doc", text, chunk_size=100, overlap=10)
    assert len(chunks) == 1
    assert chunks[0].text == text


def test_chunk_text_splits_when_over_size():
    text = "a" * 50 + "\n\n" + "b" * 50
    chunks = chunk_text("doc", text, chunk_size=60, overlap=10)
    assert len(chunks) == 2
    assert chunks[0].chunk_id == "doc::chunk-0"
    assert chunks[1].chunk_id == "doc::chunk-1"


def test_chunk_text_hard_splits_a_single_oversized_paragraph():
    text = "x" * 250
    chunks = chunk_text("doc", text, chunk_size=100, overlap=20)
    assert len(chunks) >= 3
    assert all(len(c.text) <= 100 for c in chunks)


def test_chunk_text_rejects_overlap_ge_chunk_size():
    with pytest.raises(ValueError):
        chunk_text("doc", "text", chunk_size=50, overlap=50)


def test_load_documents_parses_frontmatter(tmp_path: Path):
    doc_path = tmp_path / "example.md"
    doc_path.write_text(
        "---\ntitle: Example Doc\ncategory: troubleshooting\nservice: payment-service\n"
        "environment: production\n---\n\n# Example Doc\n\nBody text here.\n",
        encoding="utf-8",
    )
    docs = load_documents(tmp_path)
    assert len(docs) == 1
    doc = docs[0]
    assert doc.document_id == "example"
    assert doc.title == "Example Doc"
    assert doc.category == "troubleshooting"
    assert doc.service == "payment-service"
    assert doc.environment == "production"
    assert "Body text here." in doc.text


def test_load_documents_handles_missing_frontmatter(tmp_path: Path):
    doc_path = tmp_path / "no_frontmatter.md"
    doc_path.write_text("# Just a heading\n\nSome text.\n", encoding="utf-8")
    docs = load_documents(tmp_path)
    assert docs[0].title == "no_frontmatter"
    assert docs[0].category == "general"
    assert docs[0].service is None
