"""Wire contracts for the OpenAI-compatible surface.

Request models deliberately IGNORE unknown fields instead of forbidding
them: drop-in compatibility means real OpenAI clients send fields this tier
does not implement (penalties, tool definitions, ...). Response models are
narrow projections — nothing internal ever crosses the HTTP boundary.
"""
from __future__ import annotations

import time

from pydantic import BaseModel, ConfigDict, Field


class ChatMessage(BaseModel):
    model_config = ConfigDict(extra="ignore")

    role: str
    content: str


class ChatCompletionRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    model: str
    messages: list[ChatMessage] = Field(min_length=1)
    temperature: float | None = None
    stream: bool = False
    user: str | None = None


class ChatCompletionChoice(BaseModel):
    index: int = 0
    message: ChatMessage
    finish_reason: str = "stop"


class ChatCompletionUsage(BaseModel):
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class MicroEngineExtension(BaseModel):
    """Non-OpenAI fields the sprite-shell UI needs. OpenAI clients ignore
    unknown response fields, so carrying this alongside the standard payload
    keeps drop-in compatibility while exposing the character's turn state."""

    tag: str
    sprite: str | None = None
    axes: dict[str, float]


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)
    x_micro_engine: MicroEngineExtension | None = None


class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "character-pack"


class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelCard]
