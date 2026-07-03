"""Runtime configuration read from the process environment.

Everything here is infrastructure (endpoints, model names, directories).
The engine ships no character-shaped defaults: character content comes
exclusively from a loaded character pack.
"""
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of engine configuration."""

    ollama_base_url: str = "http://127.0.0.1:11434"
    chat_model: str = "gemma3:12b"
    embed_model: str = "nomic-embed-text"
    data_dir: str = "data"
    llm_timeout_s: float = 120.0
    # Ceiling for every relationship axis. Raising it (e.g. to 1000) makes the
    # same per-turn deltas a smaller fraction of the whole, so relationships
    # warm far more slowly — a global "slow-burn" knob, independent of packs.
    axis_max: float = 100.0


def load_settings() -> Settings:
    """Build settings from environment variables, falling back to defaults."""
    return Settings(
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", Settings.ollama_base_url),
        chat_model=os.getenv("CHAT_MODEL", Settings.chat_model),
        embed_model=os.getenv("EMBED_MODEL", Settings.embed_model),
        data_dir=os.getenv("DATA_DIR", Settings.data_dir),
        llm_timeout_s=float(os.getenv("LLM_TIMEOUT_S", Settings.llm_timeout_s)),
        axis_max=float(os.getenv("AXIS_MAX", Settings.axis_max)),
    )
