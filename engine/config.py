"""Runtime configuration read from the process environment (and an optional
`.env` file).

Everything here is infrastructure (endpoints, model choice, sampling,
directories). The engine ships no character-shaped defaults: character content
comes exclusively from a loaded character pack.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Settings:
    """Immutable snapshot of engine configuration."""

    # Which backend generates responses: "ollama" (local) or "openai" (cloud).
    llm_backend: str = "ollama"
    ollama_base_url: str = "http://127.0.0.1:11434"
    chat_model: str = "gemma3:12b"
    embed_model: str = "nomic-embed-text"
    # OpenAI backend (used when llm_backend == "openai"). The key is read from
    # the environment / .env and never leaves the server.
    openai_api_key: str = ""
    openai_base_url: str = "https://api.openai.com/v1"
    openai_model: str = "gpt-4o-mini"
    openai_embed_model: str = "text-embedding-3-small"
    data_dir: str = "data"
    # Where per-session relationship state and transcripts are persisted, so a
    # long correspondence continues across restarts.
    sessions_dir: str = ".local/sessions"
    # Where per-session scene state (relationship matrix + transcript) persists.
    scenes_dir: str = ".local/scenes"
    # Non-roleplay mode: forbid the character from narrating its own actions
    # (asterisk emotes, stage directions) — it stays in voice but replies as a
    # plain conversational pet-assistant. Good for showing the mechanics.
    non_rp: bool = False
    # Non-romance mode: keep every relationship strictly platonic regardless of
    # how close it grows and of what a pack's tags/stages invite. Warmth and
    # friendship still deepen; flirtation and romance are refused.
    non_romance: bool = False
    # Reply language (e.g. "Russian"). Empty = let the model answer in whatever
    # language the user writes in. A per-request field overrides this default.
    language: str = ""
    # The user's grammatical gender ("male" / "female"), so a character uses the
    # right pronouns and agreement in gendered languages. Empty = unspecified.
    # A per-request field overrides this default.
    user_gender: str = ""
    # Opt-in web lookup. When on, a turn a pack classifies as `web_lookup` runs
    # a DuckDuckGo search and grounds the reply on the snippets. Off by default:
    # the community tier ships no network access unless a deployer enables it.
    web_search: bool = False
    web_search_results: int = 3
    llm_timeout_s: float = 120.0
    # Sampling for the voicing model. Temperature is the character's "spark";
    # num_ctx is the model context window (tokens). num_ctx None = let the
    # model use its own default.
    temperature: float = 0.8
    num_ctx: int | None = None
    log_level: str = "INFO"
    # Ceiling for every relationship axis. Raising it (e.g. to 1000) makes the
    # same per-turn deltas a smaller fraction of the whole, so relationships
    # warm far more slowly — a global "slow-burn" knob, independent of packs.
    axis_max: float = 100.0


def _optional_int(name: str) -> int | None:
    value = os.getenv(name)
    return int(value) if value else None


def _bool_env(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in ("1", "true", "yes", "on")


def load_settings() -> Settings:
    """Build settings from a `.env` file (if present) and the environment.

    `load_dotenv` fills in variables from `.env` without overriding ones
    already set in the real environment, so explicit env vars still win.
    """
    load_dotenv()
    return Settings(
        llm_backend=os.getenv("LLM_BACKEND", Settings.llm_backend),
        ollama_base_url=os.getenv("OLLAMA_BASE_URL", Settings.ollama_base_url),
        chat_model=os.getenv("CHAT_MODEL", Settings.chat_model),
        embed_model=os.getenv("EMBED_MODEL", Settings.embed_model),
        openai_api_key=os.getenv("OPENAI_API_KEY", Settings.openai_api_key),
        openai_base_url=os.getenv("OPENAI_BASE_URL", Settings.openai_base_url),
        openai_model=os.getenv("OPENAI_MODEL", Settings.openai_model),
        openai_embed_model=os.getenv("OPENAI_EMBED_MODEL", Settings.openai_embed_model),
        data_dir=os.getenv("DATA_DIR", Settings.data_dir),
        sessions_dir=os.getenv("SESSIONS_DIR", Settings.sessions_dir),
        scenes_dir=os.getenv("SCENES_DIR", Settings.scenes_dir),
        non_rp=_bool_env("NON_RP", Settings.non_rp),
        non_romance=_bool_env("NON_ROMANCE", Settings.non_romance),
        language=os.getenv("LANGUAGE", Settings.language),
        user_gender=os.getenv("USER_GENDER", Settings.user_gender),
        web_search=_bool_env("WEB_SEARCH", Settings.web_search),
        web_search_results=int(os.getenv("WEB_SEARCH_RESULTS", Settings.web_search_results)),
        llm_timeout_s=float(os.getenv("LLM_TIMEOUT_S", Settings.llm_timeout_s)),
        temperature=float(os.getenv("TEMPERATURE", Settings.temperature)),
        num_ctx=_optional_int("NUM_CTX"),
        log_level=os.getenv("LOG_LEVEL", Settings.log_level),
        axis_max=float(os.getenv("AXIS_MAX", Settings.axis_max)),
    )
