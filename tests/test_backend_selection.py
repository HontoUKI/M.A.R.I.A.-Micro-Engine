"""The configured LLM_BACKEND selects the right client."""
from __future__ import annotations

from app.deps import _build_llm
from engine.config import Settings
from engine.llm import OllamaClient, OpenAIClient


def test_default_backend_is_ollama():
    assert isinstance(_build_llm(Settings()), OllamaClient)


def test_openai_backend_selected_by_setting():
    settings = Settings(llm_backend="openai", openai_api_key="sk-test")
    assert isinstance(_build_llm(settings), OpenAIClient)


def test_backend_choice_is_case_insensitive():
    settings = Settings(llm_backend="OpenAI", openai_api_key="sk-test")
    assert isinstance(_build_llm(settings), OpenAIClient)
