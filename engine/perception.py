"""Moment-tag classification.

The engine's only perception step: ask the LLM to read the latest turn in
context and pick ONE tag from the pack's closed enum. Selection is constrained
by a JSON schema (the enum lives in the schema, so the backend can only return
a declared tag). An unparseable or unknown answer retries once, then falls back
to the pack's declared `fallback_tag` — never crashes a turn.
"""
from __future__ import annotations

import json
from typing import Any

from engine.llm import LLMError, OllamaClient
from engine.prompt_manager import DialogueTurn


class TagClassifier:
    """Chooses one moment tag per turn via constrained decoding."""

    def __init__(self, llm: OllamaClient, *, max_retries: int = 1) -> None:
        self._llm = llm
        self._max_retries = max(0, max_retries)

    def classify(
        self,
        pack,
        user_message: str,
        dialogue_window: tuple[DialogueTurn, ...] = (),
    ) -> str:
        """Return a tag id guaranteed to be one the pack declared."""
        messages = _build_messages(pack, user_message, dialogue_window)
        schema = _tag_schema(pack)
        valid = {t.id for t in pack.tags}

        for _ in range(self._max_retries + 1):
            try:
                raw = self._llm.chat(messages, fmt=schema)
            except LLMError:
                break
            tag = _parse_tag(raw)
            if tag in valid:
                return tag
        return pack.meta.fallback_tag


def _build_messages(
    pack, user_message: str, dialogue_window: tuple[DialogueTurn, ...]
) -> list[dict[str, str]]:
    lines = [
        "You are a classifier. Read the latest user message in context and "
        "choose the single tag that best describes the moment.",
        'Respond only as JSON of the form {"tag": "<id>"}.',
        "Available tags:",
    ]
    lines.extend(f"- {t.id}: {t.description}" for t in pack.tags)
    messages: list[dict[str, str]] = [{"role": "system", "content": "\n".join(lines)}]
    messages.extend({"role": t.role, "content": t.content} for t in dialogue_window)
    messages.append({"role": "user", "content": user_message})
    return messages


def _tag_schema(pack) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"tag": {"type": "string", "enum": [t.id for t in pack.tags]}},
        "required": ["tag"],
    }


def _parse_tag(raw: str) -> str | None:
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None
    if isinstance(data, dict) and isinstance(data.get("tag"), str):
        return data["tag"]
    return None
