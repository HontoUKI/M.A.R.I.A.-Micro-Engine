"""Shared helper: build a validated CharacterPack in-memory for tests."""
from __future__ import annotations

from engine.pack.models import CharacterPack


def make_pack(**overrides) -> CharacterPack:
    data = {
        "spec_version": 1,
        "meta": {
            "name": "aria",
            "display_name": "Aria",
            "version": "0.1.0",
            "license": "CC-BY-4.0",
            "author": "example",
            "fallback_tag": "neutral",
        },
        "identity": "You are Aria, a calm librarian.",
        "axes": {
            "affection": {"min": 0, "max": 100, "start": 20},
            "trust": {"min": 0, "max": 100, "start": 10},
            "bond": {"min": 0, "max": 100, "start": 0},
        },
        "tags": [
            {"id": "warmth", "description": "The user is warm.", "sentiment": "positive"},
            {"id": "hostility", "description": "The user is hostile.", "sentiment": "negative"},
            {"id": "neutral", "description": "Ordinary exchange.", "sentiment": "neutral"},
        ],
        "deltas": {
            "warmth": {"affection": 5.0, "trust": 3.0, "bond": 0.5},
            "hostility": {"affection": -6.0, "trust": -4.0, "bond": -0.2},
            "neutral": {"affection": 0.0, "trust": 0.0, "bond": 0.0},
        },
        "blocks": {
            "warmth": "Let the warmth land.",
            "hostility": "Stay guarded.",
            "neutral": "",
        },
        "decay": {"affection": 2.0, "trust": 1.0, "bond": 0.1},
        "sprites": {},
    }
    data.update(overrides)
    return CharacterPack.model_validate(data)
