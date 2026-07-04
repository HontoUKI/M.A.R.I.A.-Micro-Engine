"""Engine service — the seam between the HTTP layer and the runtime.

Holds the pack registry, the shared LLM client and the session store, and
turns an OpenAI-style request into one character turn. Constructed with its
dependencies injected so the API can be tested against a stub LLM.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.contracts import ChatMessage
from app.sessions import SessionStore
from engine.character import CharacterRuntime, TurnResult
from engine.llm import OllamaClient
from engine.prompt_manager import DialogueTurn, PromptManager
from engine.registry import PackRegistry
from engine.state import DEFAULT_AXIS_MAX
from engine.web import WebSearcher


class UnknownModelError(Exception):
    """Requested `model` is not a loaded pack."""


class EmptyConversationError(Exception):
    """The message list has no trailing user message to drive a turn."""


@dataclass
class EngineService:
    registry: PackRegistry
    llm: OllamaClient
    axis_max: float = DEFAULT_AXIS_MAX
    non_rp: bool = False
    web_search: WebSearcher | None = None
    sessions_dir: str = ".local/sessions"
    sessions: SessionStore = None  # type: ignore[assignment]
    prompt_manager: PromptManager = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.sessions is None:
            self.sessions = SessionStore(axis_max=self.axis_max, root=self.sessions_dir)
        if self.prompt_manager is None:
            self.prompt_manager = PromptManager()

    def model_names(self) -> list[str]:
        return self.registry.names()

    def has_model(self, name: str) -> bool:
        return name in self.registry

    def complete(
        self, model: str, messages: list[ChatMessage], *, session_key: str
    ) -> TurnResult:
        pack = self.registry.get(model)
        if pack is None:
            raise UnknownModelError(model)

        driver, window = _split_messages(messages)
        kernel = self.sessions.kernel_for(session_key, pack)
        runtime = CharacterRuntime(
            pack,
            self.llm,
            state=kernel,
            prompt_manager=self.prompt_manager,
            axis_max=self.axis_max,
            non_rp=self.non_rp,
            web_search=self.web_search,
        )
        result = runtime.respond(driver, window)
        self.sessions.record_turn(
            session_key, pack, kernel, user_message=driver, result=result
        )
        return result


def _split_messages(
    messages: list[ChatMessage],
) -> tuple[str, tuple[DialogueTurn, ...]]:
    """Last user message drives the turn; preceding user/assistant turns form
    the dialogue window. Client system messages are ignored — the pack's
    identity is the authoritative system voice."""
    if not messages or messages[-1].role != "user":
        raise EmptyConversationError("conversation must end with a user message")

    driver = messages[-1].content
    window = tuple(
        DialogueTurn(m.role, m.content)
        for m in messages[:-1]
        if m.role in ("user", "assistant")
    )
    return driver, window
