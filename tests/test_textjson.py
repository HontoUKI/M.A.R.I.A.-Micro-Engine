"""Lenient JSON parsing tolerates the code fences some models add."""
from __future__ import annotations

from engine.textjson import loads_lenient


def test_plain_json():
    assert loads_lenient('{"tag": "warmth"}') == {"tag": "warmth"}


def test_json_fence_with_language_tag():
    raw = '```json\n{"tag": "warmth", "target": "user"}\n```'
    assert loads_lenient(raw) == {"tag": "warmth", "target": "user"}


def test_bare_fence():
    assert loads_lenient('```\n{"speaker": "kaguya"}\n```') == {"speaker": "kaguya"}


def test_surrounding_whitespace():
    assert loads_lenient('  \n {"a": 1}\n ') == {"a": 1}


def test_garbage_returns_none():
    assert loads_lenient("not json at all") is None
    assert loads_lenient("```json\nnope\n```") is None


def test_non_string_returns_none():
    assert loads_lenient(None) is None
    assert loads_lenient(42) is None
