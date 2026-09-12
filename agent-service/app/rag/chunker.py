"""Splits document text into overlapping chunks for embedding.

Chunking is paragraph-aware (splits on blank lines first) so a chunk
boundary doesn't land mid-sentence when a paragraph fits within
`chunk_size`; only paragraphs longer than `chunk_size` get hard-split with
character overlap. Sizes are in characters, not tokens — simple and
deterministic, no tokenizer needed at chunk time.
"""
from dataclasses import dataclass


@dataclass
class Chunk:
    chunk_id: str
    text: str
    index: int


def chunk_text(document_id: str, text: str, chunk_size: int, overlap: int) -> list[Chunk]:
    if overlap >= chunk_size:
        raise ValueError("overlap must be smaller than chunk_size")

    paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
    chunks: list[Chunk] = []
    buffer = ""

    for paragraph in paragraphs:
        candidate = f"{buffer}\n\n{paragraph}" if buffer else paragraph
        if len(candidate) <= chunk_size:
            buffer = candidate
            continue

        if buffer:
            chunks.append(_make_chunk(document_id, buffer, len(chunks)))
        buffer = paragraph
        while len(buffer) > chunk_size:
            chunks.append(_make_chunk(document_id, buffer[:chunk_size], len(chunks)))
            buffer = buffer[chunk_size - overlap :]

    if buffer:
        chunks.append(_make_chunk(document_id, buffer, len(chunks)))
    return chunks


def _make_chunk(document_id: str, text: str, index: int) -> Chunk:
    return Chunk(chunk_id=f"{document_id}::chunk-{index}", text=text, index=index)
