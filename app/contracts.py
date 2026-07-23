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
    # Micro-Engine extensions (OpenAI clients simply omit them): force the reply
    # language and tell the character the user's grammatical gender. Both
    # override the server-level defaults for this turn.
    language: str | None = None
    user_gender: str | None = None


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
    stage: str | None = None
    stage_changed: bool = False


class ChatCompletionResponse(BaseModel):
    id: str
    object: str = "chat.completion"
    created: int = Field(default_factory=lambda: int(time.time()))
    model: str
    choices: list[ChatCompletionChoice]
    usage: ChatCompletionUsage = Field(default_factory=ChatCompletionUsage)
    x_micro_engine: MicroEngineExtension | None = None


class SceneAdvanceRequest(BaseModel):
    """Advance a scene by one turn (v0.2). `message` is the user's line in group
    chat (optional in autonomous play); `speaker` optionally names who acts."""

    model_config = ConfigDict(extra="ignore")

    user: str | None = None
    message: str | None = None
    speaker: str | None = None


class SceneRunRequest(BaseModel):
    """Play/narrator mode (v0.2): feed a stage cue and let the cast act among
    themselves for up to `max_turns` (the server caps it)."""

    model_config = ConfigDict(extra="ignore")

    user: str | None = None
    cue: str | None = None
    max_turns: int | None = None


class SceneBackdropRequest(BaseModel):
    """Upload an image (base64, optionally a data: URL) to caption and pin as the
    scene's backdrop (v0.2, vision-capable Ollama models only)."""

    model_config = ConfigDict(extra="ignore")

    user: str | None = None
    image: str


class WitnessOut(BaseModel):
    actor: str
    tag: str
    target: str
    feeling: dict[str, float]


class SceneTurnOut(BaseModel):
    """One scene turn, projected for the client (no internal state leaks)."""

    speaker: str
    reply: str
    tag: str
    target: str
    feeling: dict[str, float]
    witnessed: list[WitnessOut] = Field(default_factory=list)


class SceneCard(BaseModel):
    id: str
    display_name: str
    cast: list[str]
    mode: str


class SceneList(BaseModel):
    object: str = "list"
    data: list[SceneCard]


class ModelCard(BaseModel):
    id: str
    object: str = "model"
    created: int = Field(default_factory=lambda: int(time.time()))
    owned_by: str = "character-pack"


class ModelList(BaseModel):
    object: str = "list"
    data: list[ModelCard]
