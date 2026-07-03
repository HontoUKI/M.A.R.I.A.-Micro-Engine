"""Dependency wiring for the API layer.

Builds the singleton `EngineService` from environment settings on first use.
Endpoints depend on `get_service`; tests override it via FastAPI's
`dependency_overrides` to inject a service backed by a stub LLM.
"""
from __future__ import annotations

import os

from app.service import EngineService
from engine.config import load_settings
from engine.llm import OllamaClient
from engine.logging_config import configure as configure_logging
from engine.registry import PackRegistry

CHARACTERS_DIR_ENV = "CHARACTERS_DIR"
_DEFAULT_CHARACTERS_DIR = "characters"

_service: EngineService | None = None


def _build_service() -> EngineService:
    settings = load_settings()
    configure_logging(settings.log_level)
    characters_dir = os.getenv(CHARACTERS_DIR_ENV, _DEFAULT_CHARACTERS_DIR)
    registry = PackRegistry.from_dir(characters_dir)
    llm = OllamaClient(
        settings.ollama_base_url,
        settings.chat_model,
        settings.embed_model,
        timeout_s=settings.llm_timeout_s,
        temperature=settings.temperature,
        num_ctx=settings.num_ctx,
    )
    return EngineService(registry=registry, llm=llm, axis_max=settings.axis_max)


def get_service() -> EngineService:
    global _service
    if _service is None:
        _service = _build_service()
    return _service
