"""Tests for tolerant JSON extraction."""

from __future__ import annotations

import pytest

from teacher_copilot.providers.json_utils import JSONExtractionError, extract_json


def test_clean_json() -> None:
    assert extract_json('{"intent": "grading", "confidence": 0.9}') == {
        "intent": "grading",
        "confidence": 0.9,
    }


def test_fenced_json() -> None:
    text = '```json\n{"a": 1, "b": [2, 3]}\n```'
    assert extract_json(text) == {"a": 1, "b": [2, 3]}


def test_prose_then_json() -> None:
    text = 'Sure! Here is the classification you asked for:\n{"intent": "career"}'
    assert extract_json(text) == {"intent": "career"}


def test_trailing_text_after_json() -> None:
    text = '{"status": "graded"} — hope that helps!'
    assert extract_json(text) == {"status": "graded"}


def test_nested_object_span() -> None:
    text = 'result: {"scores": [{"name": "x", "marks": 2}], "total": 2} done'
    assert extract_json(text) == {"scores": [{"name": "x", "marks": 2}], "total": 2}


def test_genuinely_malformed_raises_with_raw() -> None:
    text = "there is definitely no json here"
    with pytest.raises(JSONExtractionError) as excinfo:
        extract_json(text)
    assert excinfo.value.raw == text


def test_empty_raises() -> None:
    with pytest.raises(JSONExtractionError):
        extract_json("   ")


def test_broken_braces_raise() -> None:
    with pytest.raises(JSONExtractionError):
        extract_json('{"intent": ')


def test_non_object_json_raises() -> None:
    # A JSON array is valid JSON but not an object; we require an object.
    with pytest.raises(JSONExtractionError):
        extract_json("[1, 2, 3]")
