"""Lenient JSON parsing for LLM structured output.

Even with a JSON schema forced via the backend's `format`/`response_format`,
some models still wrap their answer in a Markdown code fence (```json ... ```).
A strict `json.loads` then throws and the caller falls back — silently losing a
perfectly good classification. This strips a surrounding fence before parsing.
"""
from __future__ import annotations

import json
import re
from typing import Any

_LEADING_FENCE = re.compile(r"^```[a-zA-Z]*\s*")
_TRAILING_FENCE = re.compile(r"\s*```$")


def loads_lenient(raw: object) -> Any | None:
    """Parse JSON that may be wrapped in a Markdown code fence. Returns None on
    anything unparseable (never raises)."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = _LEADING_FENCE.sub("", text)
        text = _TRAILING_FENCE.sub("", text).strip()
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
