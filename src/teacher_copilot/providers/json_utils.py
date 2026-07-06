"""Tolerant JSON extraction for LLM output.

Reasoning-tuned models (the gpt-oss family especially) love to wrap JSON in
markdown fences or prefix it with a sentence of prose, even when told not to. Rather
than fight that in every prompt, :func:`extract_json` is the standard defense: it
pulls the first balanced-looking ``{...}`` span out of the text and parses it.

On failure it raises :class:`JSONExtractionError` with the raw text attached, so
callers can retry with a corrective nudge or preserve the raw output for review.
"""

from __future__ import annotations

import json
from typing import Any


class JSONExtractionError(ValueError):
    """Raised when no JSON object can be recovered from a piece of text."""

    def __init__(self, message: str, *, raw: str) -> None:
        super().__init__(message)
        self.raw = raw


def _try_load(candidate: str) -> Any:
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        return None


def extract_json(text: str) -> dict[str, Any]:
    """Extract and parse the first JSON object embedded in ``text``.

    Handles: clean JSON, ```json fenced blocks, prose-before-JSON, and
    trailing-text-after-JSON. Raises :class:`JSONExtractionError` (with ``raw``) if
    no JSON object can be parsed, or if the parsed value is not an object.
    """
    if not text or not text.strip():
        raise JSONExtractionError("empty response", raw=text)

    stripped = text.strip()

    # Fast path: the whole thing is already valid JSON.
    parsed = _try_load(stripped)
    if parsed is None:
        # Fallback: carve out the first '{' … last '}' span (skips fences/prose).
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end < start:
            raise JSONExtractionError("no JSON object found in text", raw=text)
        parsed = _try_load(stripped[start : end + 1])

    if parsed is None:
        raise JSONExtractionError("could not parse JSON from text", raw=text)
    if not isinstance(parsed, dict):
        raise JSONExtractionError("parsed JSON is not an object", raw=text)
    return parsed
