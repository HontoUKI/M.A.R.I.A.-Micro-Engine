"""Dependency wiring for the API layer.

Builds the singleton `EngineService` from environment settings on first use.
Endpoints depend on `get_service`; tests override it via FastAPI's
`dependency_overrides` to inject a service backed by a stub LLM.
"""
from __future__ import annotations

import os

from app.service import EngineService
from engine.config import Settings, load_settings
from engine.llm import OllamaClient, OpenAIClient
from engine.logging_config import configure as configure_logging
from engine.logging_config import get_logger
from engine.registry import PackRegistry
from engine.web import DuckDuckGoSearcher

_log = get_logger("deps")

CHARACTERS_DIR_ENV = "CHARACTERS_DIR"
_DEFAULT_CHARACTERS_DIR = "characters"

_service: EngineService | None = None


def _build_llm(settings: Settings):
    """Build the response backend from settings (Ollama by default)."""
    if settings.llm_backend.lower() == "openai":
        if not settings.openai_api_key:
            _log.warning("LLM_BACKEND=openai but OPENAI_API_KEY is empty; calls will fail")
        return OpenAIClient(
            settings.openai_api_key,
            base_url=settings.openai_base_url,
            chat_model=settings.openai_model,
            embed_model=settings.openai_embed_model,
            timeout_s=settings.llm_timeout_s,
            temperature=settings.temperature,
        )
    return OllamaClient(
        settings.ollama_base_url,
        settings.chat_model,
        settings.embed_model,
        timeout_s=settings.llm_timeout_s,
        temperature=settings.temperature,
        num_ctx=settings.num_ctx,
    )


def _build_service() -> EngineService:
    settings = load_settings()
    configure_logging(settings.log_level)
    characters_dir = os.getenv(CHARACTERS_DIR_ENV, _DEFAULT_CHARACTERS_DIR)
    registry = PackRegistry.from_dir(characters_dir)
    web_search = (
        DuckDuckGoSearcher(limit=settings.web_search_results) if settings.web_search else None
    )
    return EngineService(
        registry=registry,
        llm=_build_llm(settings),
        axis_max=settings.axis_max,
        non_rp=settings.non_rp,
        non_romance=settings.non_romance,
        web_search=web_search,
        sessions_dir=settings.sessions_dir,
    )


def get_service() -> EngineService:
    global _service
    if _service is None:
        _service = _build_service()
    return _service
