"""Curriculum ingestion: load source docs, chunk them, ready for embedding."""

from teacher_copilot.ingestion.chunker import Chunk, chunk_document
from teacher_copilot.ingestion.loader import LoadedDoc, load_documents

__all__ = ["Chunk", "LoadedDoc", "chunk_document", "load_documents"]
