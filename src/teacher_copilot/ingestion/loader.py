"""Load curriculum source documents into text + metadata.

Supports ``.txt``, ``.md`` (with optional YAML-ish front-matter), and ``.pdf`` (via
pypdf). Metadata (subject / grade / board) can come from markdown front-matter or a
sidecar ``<name>.json`` next to the file. Scanned/imageless PDFs yield no extractable
text and are skipped with a warning — OCR is out of scope here.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from pydantic import BaseModel, Field
from pypdf import PdfReader

logger = logging.getLogger("teacher_copilot.ingestion")

_TEXT_SUFFIXES = {".txt", ".md"}
_META_KEYS = ("subject", "grade", "board")


class LoadedDoc(BaseModel):
    """A source document reduced to plain text plus its curriculum metadata."""

    text: str = Field(description="Extracted plain text.")
    source_filename: str = Field(description="Original filename (used as the citation source).")
    subject: str | None = Field(default=None)
    grade: str | None = Field(default=None)
    board: str | None = Field(default=None)


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Parse a leading ``---`` front-matter block of ``key: value`` lines.

    Returns ``(metadata, body)``. Deliberately tiny (no YAML dependency): only flat
    ``key: value`` pairs are understood, which is all our sidecar metadata needs.
    """
    if not text.startswith("---"):
        return {}, text
    lines = text.splitlines()
    if lines[0].strip() != "---":
        return {}, text
    meta: dict[str, str] = {}
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            body = "\n".join(lines[idx + 1 :]).lstrip("\n")
            return meta, body
        if ":" in lines[idx]:
            key, _, value = lines[idx].partition(":")
            meta[key.strip().lower()] = value.strip()
    return {}, text  # no closing fence -> treat as body


def _sidecar_metadata(path: Path) -> dict[str, str]:
    sidecar = path.with_suffix(".json")
    if not sidecar.exists():
        return {}
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("ignoring unreadable sidecar %s: %s", sidecar.name, exc)
        return {}
    return {k: str(v) for k, v in data.items() if k in _META_KEYS}


def _read_pdf(path: Path) -> str:
    reader = PdfReader(str(path))
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n\n".join(p.strip() for p in pages if p.strip())


def _load_one(path: Path) -> LoadedDoc | None:
    meta: dict[str, str] = _sidecar_metadata(path)
    if path.suffix.lower() in _TEXT_SUFFIXES:
        text = path.read_text(encoding="utf-8")
        front, body = _parse_front_matter(text)
        meta = {**front, **meta}  # sidecar wins over front-matter
        text = body
    elif path.suffix.lower() == ".pdf":
        text = _read_pdf(path)
        if not text.strip():
            logger.warning("skipping '%s': no extractable text (scanned/image PDF?)", path.name)
            return None
    else:
        return None

    if not text.strip():
        logger.warning("skipping '%s': empty document", path.name)
        return None
    return LoadedDoc(
        text=text,
        source_filename=path.name,
        subject=meta.get("subject"),
        grade=meta.get("grade"),
        board=meta.get("board"),
    )


def load_documents(directory: str | Path) -> list[LoadedDoc]:
    """Load every supported document under ``directory`` (non-recursive)."""
    root = Path(directory)
    if not root.exists():
        logger.warning("curriculum directory %s does not exist", root)
        return []
    docs: list[LoadedDoc] = []
    for path in sorted(root.iterdir()):
        if not path.is_file() or path.suffix.lower() not in {*_TEXT_SUFFIXES, ".pdf"}:
            continue
        doc = _load_one(path)
        if doc is not None:
            docs.append(doc)
    return docs
