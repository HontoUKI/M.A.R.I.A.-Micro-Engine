"""Speaker selection — who talks next in a scene.

The Director decides whose turn it is. Model-directed selection is the twin of
the moment-tag classifier one level up: instead of picking a tag from a closed
enum, it picks an **actor** from the cast, via constrained decoding. An
unparseable or unknown answer retries once, then returns None so the caller can
fall back (round-robin, last-addressed, ...). Narrator-directed selection needs
no model — the caller simply names the speaker.
"""
from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from engine.llm import LLMError, OllamaClient
from engine.textjson import loads_lenient


class SpeakerSelector:
    """Model-directed pick of the next speaker from a cast."""

    def __init__(self, llm: OllamaClient, *, max_retries: int = 1) -> None:
        self._llm = llm
        self._max_retries = max(0, max_retries)

    def choose(
        self,
        actors: Sequence[str],
        context: str,
        trigger: str,
        *,
        descriptions: dict[str, str] | None = None,
    ) -> str | None:
        """Return the actor most likely to speak next, or None if the model
        can't decide (the caller then falls back)."""
        actors = list(actors)
        if not actors:
            return None
        if len(actors) == 1:
            return actors[0]

        schema = _speaker_schema(actors)
        messages = _selector_messages(actors, context, trigger, descriptions or {})
        valid = set(actors)
        for _ in range(self._max_retries + 1):
            try:
                raw = self._llm.chat(messages, fmt=schema, options={"temperature": 0.0})
            except LLMError:
                break
            pick = _parse_speaker(raw)
            if pick in valid:
                return pick
        return None


def _selector_messages(
    actors: list[str], context: str, trigger: str, descriptions: dict[str, str]
) -> list[dict[str, str]]:
    lines = [
        "You are the director of a scene. Given what just happened, choose the "
        "single character who would most naturally speak or react next.",
        'Respond only as JSON of the form {"speaker": "<id>"}.',
        "The cast:",
    ]
    for actor in actors:
        desc = descriptions.get(actor, "")
        lines.append(f"- {actor}: {desc}" if desc else f"- {actor}")
    system = "\n".join(lines)
    user = (context + "\n\n" if context else "") + f"Just now: {trigger}"
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _speaker_schema(actors: list[str]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {"speaker": {"type": "string", "enum": actors}},
        "required": ["speaker"],
    }


def _parse_speaker(raw: str) -> str | None:
    data = loads_lenient(raw)
    if isinstance(data, dict) and isinstance(data.get("speaker"), str):
        return data["speaker"]
    return None


def next_round_robin(actors: Sequence[str], last: str | None) -> str:
    """Deterministic fallback: the actor after `last`, wrapping around."""
    actors = list(actors)
    if not actors:
        raise ValueError("cannot pick a speaker from an empty cast")
    if last is None or last not in actors:
        return actors[0]
    return actors[(actors.index(last) + 1) % len(actors)]
