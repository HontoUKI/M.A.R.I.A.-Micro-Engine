"""Engine service — the seam between the HTTP layer and the runtime.

Holds the pack registry, the shared LLM client and the session store, and
turns an OpenAI-style request into one character turn. Constructed with its
dependencies injected so the API can be tested against a stub LLM.
"""
from __future__ import annotations

from dataclasses import dataclass

from app.contracts import ChatMessage
from app.scenes import SceneStore
from app.sessions import SessionStore
from engine.character import CharacterRuntime, TurnResult
from engine.llm import OllamaClient
from engine.prompt_manager import DialogueTurn, PromptManager
from engine.registry import PackRegistry
from engine.scene.registry import SceneRegistry
from engine.scene.runtime import SceneTurnResult
from engine.state import DEFAULT_AXIS_MAX
from engine.vision import caption_backdrop
from engine.web import WebSearcher


class UnknownModelError(Exception):
    """Requested `model` is not a loaded pack."""


class EmptyConversationError(Exception):
    """The message list has no trailing user message to drive a turn."""


class UnknownSceneError(Exception):
    """Requested scene is not loaded."""


class SceneUnavailableError(Exception):
    """A scene's cast references a character pack that isn't loaded."""


@dataclass
class EngineService:
    registry: PackRegistry
    llm: OllamaClient
    axis_max: float = DEFAULT_AXIS_MAX
    non_rp: bool = False
    non_romance: bool = False
    language: str = ""
    user_gender: str = ""
    vision_model: str = ""
    web_search: WebSearcher | None = None
    sessions_dir: str = ".local/sessions"
    scenes_dir: str = ".local/scenes"
    scene_registry: SceneRegistry = None  # type: ignore[assignment]
    sessions: SessionStore = None  # type: ignore[assignment]
    scene_store: SceneStore = None  # type: ignore[assignment]
    prompt_manager: PromptManager = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.sessions is None:
            self.sessions = SessionStore(axis_max=self.axis_max, root=self.sessions_dir)
        if self.scene_registry is None:
            self.scene_registry = SceneRegistry()
        if self.scene_store is None:
            self.scene_store = SceneStore(self.llm, axis_max=self.axis_max, root=self.scenes_dir)
        if self.prompt_manager is None:
            self.prompt_manager = PromptManager()

    def model_names(self) -> list[str]:
        return self.registry.names()

    def has_model(self, name: str) -> bool:
        return name in self.registry

    def _require_pack(self, model: str):
        pack = self.registry.get(model)
        if pack is None:
            raise UnknownModelError(model)
        return pack

    def history_days(self, model: str, session_key: str) -> list[str]:
        return self.sessions.transcript_days(session_key, self._require_pack(model))

    def history(self, model: str, session_key: str, day: str | None = None) -> list[dict]:
        return self.sessions.read_transcript(session_key, self._require_pack(model), day)

    def clear_history(self, model: str, session_key: str, day: str | None = None) -> int:
        return self.sessions.clear_transcript(session_key, self._require_pack(model), day)

    def reset_relationship(self, model: str, session_key: str) -> None:
        self.sessions.reset_state(session_key, self._require_pack(model))

    def complete(
        self,
        model: str,
        messages: list[ChatMessage],
        *,
        session_key: str,
        language: str | None = None,
        user_gender: str | None = None,
    ) -> TurnResult:
        pack = self._require_pack(model)

        driver, window = _split_messages(messages)
        kernel = self.sessions.kernel_for(session_key, pack)
        runtime = CharacterRuntime(
            pack,
            self.llm,
            state=kernel,
            prompt_manager=self.prompt_manager,
            axis_max=self.axis_max,
            non_rp=self.non_rp,
            non_romance=self.non_romance,
            # Per-request values override the server-level defaults.
            language=self.language if language is None else language,
            user_gender=self.user_gender if user_gender is None else user_gender,
            web_search=self.web_search,
        )
        result = runtime.respond(driver, window)
        self.sessions.record_turn(
            session_key, pack, kernel, user_message=driver, result=result
        )
        return result

    # ------------------------------------------------------------- scenes (v0.2)

    def scene_names(self) -> list[str]:
        return self.scene_registry.names()

    def has_scene(self, name: str) -> bool:
        return name in self.scene_registry

    def scene_cards(self) -> list[dict]:
        cards = []
        for name in self.scene_registry.names():
            scene = self.scene_registry.get(name)
            cards.append({
                "id": scene.meta.name,
                "display_name": scene.meta.display_name,
                "cast": list(scene.cast),
                "mode": scene.mode,
            })
        return cards

    def _require_scene(self, name: str):
        scene = self.scene_registry.get(name)
        if scene is None:
            raise UnknownSceneError(name)
        return scene

    def _scene_packs(self, scene) -> dict:
        packs = {}
        for actor in scene.cast:
            pack = self.registry.get(actor)
            if pack is None:
                raise SceneUnavailableError(
                    f"scene {scene.meta.name!r} needs character pack {actor!r}, "
                    f"which is not loaded"
                )
            packs[actor] = pack
        return packs

    def advance_scene(
        self,
        scene_name: str,
        session_key: str,
        *,
        message: str | None = None,
        speaker: str | None = None,
    ) -> SceneTurnResult:
        scene = self._require_scene(scene_name)
        packs = self._scene_packs(scene)
        runtime = self.scene_store.runtime_for(session_key, scene, packs)
        result = runtime.advance(message, speaker=speaker)
        self.scene_store.save(session_key, scene, runtime)
        return result

    def run_scene(
        self,
        scene_name: str,
        session_key: str,
        *,
        cue: str | None = None,
        max_turns: int = 1,
    ) -> list[SceneTurnResult]:
        scene = self._require_scene(scene_name)
        packs = self._scene_packs(scene)
        runtime = self.scene_store.runtime_for(session_key, scene, packs)
        results = runtime.run(cue, max_turns=max_turns)
        self.scene_store.save(session_key, scene, runtime)
        return results

    def set_scene_backdrop(
        self, scene_name: str, session_key: str, image_b64: str
    ) -> str:
        """Caption an uploaded image and pin it as the scene's backdrop."""
        scene = self._require_scene(scene_name)
        packs = self._scene_packs(scene)
        runtime = self.scene_store.runtime_for(session_key, scene, packs)
        caption = caption_backdrop(self.llm, image_b64, model=self.vision_model or None)
        runtime.set_backdrop(caption)
        self.scene_store.save(session_key, scene, runtime)
        return caption

    def scene_backdrop(self, scene_name: str, session_key: str) -> str:
        return self.scene_store.backdrop(session_key, self._require_scene(scene_name))

    def scene_transcript(self, scene_name: str, session_key: str) -> list[dict]:
        return self.scene_store.transcript(session_key, self._require_scene(scene_name))

    def scene_matrix(self, scene_name: str, session_key: str) -> dict:
        return self.scene_store.matrix(session_key, self._require_scene(scene_name))

    def reset_scene(self, scene_name: str, session_key: str) -> None:
        self.scene_store.reset(session_key, self._require_scene(scene_name))


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
