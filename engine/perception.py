"""Moment-tag classification.

The engine's only perception step: ask the LLM to read the latest turn in
context and pick ONE tag from the pack's closed enum. Selection is constrained
by a JSON schema (the enum lives in the schema, so the backend can only return
a declared tag). An unparseable or unknown answer retries once, then falls back
to the pack's declared `fallback_tag` — never crashes a turn.
"""
from __future__ import annotations

from typing import Any

from engine.llm import LLMError, OllamaClient
from engine.prompt_manager import DialogueTurn
from engine.textjson import loads_lenient

# The classifier only needs recent context to read the current moment. Feeding
# it the whole conversation makes the prompt balloon on long chats and degrades
# structured-output adherence, so cap it to the last few turns.
_CONTEXT_TURNS = 6


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
        *,
        ratio: float | None = None,
    ) -> str:
        """Return a tag id guaranteed to be one the pack declared.

        When `ratio` (closeness, 0..1) is given, tags whose availability window
        excludes it are hidden from the model — a gated tag simply can't be
        chosen out of its stage. The fallback tag is always offered, so there is
        always at least one valid choice.
        """
        tags = _available_tags(pack, ratio)
        messages = _build_messages(tags, user_message, dialogue_window)
        schema = _tag_schema(tags)
        valid = {t.id for t in tags}

        for _ in range(self._max_retries + 1):
            try:
                # Temperature 0: classification stays deterministic no matter
                # how "sparky" the character's voicing temperature is set.
                raw = self._llm.chat(messages, fmt=schema, options={"temperature": 0.0})
            except LLMError:
                break
            tag = _parse_tag(raw)
            if tag in valid:
                return tag
        return pack.meta.fallback_tag


def _available_tags(pack, ratio: float | None) -> list:
    """The tags offered this turn: all of them, or — when a ratio is given —
    only those whose window covers it, with the fallback always kept."""
    if ratio is None:
        return list(pack.tags)
    fallback = pack.meta.fallback_tag
    available = [t for t in pack.tags if t.available_at(ratio) or t.id == fallback]
    return available or list(pack.tags)


def _build_messages(
    tags, user_message: str, dialogue_window: tuple[DialogueTurn, ...]
) -> list[dict[str, str]]:
    lines = [
        "You are a classifier. Read the latest user message in context and "
        "choose the single tag that best describes the moment.",
        'Respond only as JSON of the form {"tag": "<id>"}.',
        "Available tags:",
    ]
    lines.extend(f"- {t.id}: {t.description}" for t in tags)
    messages: list[dict[str, str]] = [{"role": "system", "content": "\n".join(lines)}]
    recent = dialogue_window[-_CONTEXT_TURNS:] if _CONTEXT_TURNS else ()
    messages.extend({"role": t.role, "content": t.content} for t in recent)
    messages.append({"role": "user", "content": user_message})
    return messages


def _tag_schema(tags) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"tag": {"type": "string", "enum": [t.id for t in tags]}},
        "required": ["tag"],
    }


def _parse_tag(raw: str) -> str | None:
    data = loads_lenient(raw)
    if isinstance(data, dict) and isinstance(data.get("tag"), str):
        return data["tag"]
    return None
