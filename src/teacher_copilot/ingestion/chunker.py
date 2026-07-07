"""Structure-aware chunking for curriculum documents.

Splits on blank-line paragraph boundaries and markdown headings rather than cutting
mid-sentence, then greedily packs blocks up to a target size with a small overlap so
context isn't lost across chunk edges. Deliberately dependency-light — no
``unstructured``/NLTK — a token is approximated as ~4 characters, which is plenty
accurate for sizing chunks.
"""

from __future__ import annotations

import re

from pydantic import BaseModel, Field

from teacher_copilot.ingestion.loader import LoadedDoc

_TARGET_TOKENS = 650
_OVERLAP_TOKENS = 80
_CHARS_PER_TOKEN = 4

_BLOCK_SPLIT_RE = re.compile(r"\n\s*\n")


class Chunk(BaseModel):
    """One retrievable chunk of a source document, with its provenance metadata."""

    text: str = Field(description="Chunk text.")
    source: str = Field(description="Source filename.")
    subject: str | None = Field(default=None)
    grade: str | None = Field(default=None)
    board: str | None = Field(default=None)
    chunk_index: int = Field(description="0-based position of this chunk within its source.")


def _estimate_tokens(text: str) -> int:
    return max(1, len(text) // _CHARS_PER_TOKEN)


def _is_heading(block: str) -> bool:
    stripped = block.lstrip()
    if stripped.startswith("#"):
        return True
    # A short, single-line all-caps block reads as a section header.
    return len(block.splitlines()) == 1 and len(block) < 80 and block.strip().isupper()


def _overlap_tail(blocks: list[str], overlap_tokens: int) -> list[str]:
    """Return the trailing blocks of a chunk that fit within ``overlap_tokens``."""
    tail: list[str] = []
    running = 0
    for block in reversed(blocks):
        running += _estimate_tokens(block)
        if running > overlap_tokens and tail:
            break
        tail.insert(0, block)
    return tail


def chunk_text(
    text: str, *, target_tokens: int = _TARGET_TOKENS, overlap_tokens: int = _OVERLAP_TOKENS
) -> list[str]:
    """Split ``text`` into overlapping, structure-aware chunks."""
    blocks = [b.strip() for b in _BLOCK_SPLIT_RE.split(text.strip()) if b.strip()]
    if not blocks:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_tokens = 0

    for block in blocks:
        block_tokens = _estimate_tokens(block)
        # Start a fresh chunk if this block would overflow, or if it's a heading and
        # the current chunk is already substantial (keep sections together).
        overflow = current and current_tokens + block_tokens > target_tokens
        heading_boundary = current and _is_heading(block) and current_tokens > target_tokens // 2
        if overflow or heading_boundary:
            chunks.append("\n\n".join(current))
            current = _overlap_tail(current, overlap_tokens)
            current_tokens = sum(_estimate_tokens(b) for b in current)
        current.append(block)
        current_tokens += block_tokens

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def chunk_document(
    doc: LoadedDoc, *, target_tokens: int = _TARGET_TOKENS, overlap_tokens: int = _OVERLAP_TOKENS
) -> list[Chunk]:
    """Chunk a :class:`LoadedDoc`, attaching provenance metadata to each chunk."""
    pieces = chunk_text(doc.text, target_tokens=target_tokens, overlap_tokens=overlap_tokens)
    return [
        Chunk(
            text=piece,
            source=doc.source_filename,
            subject=doc.subject,
            grade=doc.grade,
            board=doc.board,
            chunk_index=index,
        )
        for index, piece in enumerate(pieces)
    ]
