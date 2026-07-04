"""Character runtime — one turn, end to end.

Composes the loaded pack, the numeric state kernel, optional vector memory,
the tag classifier and the prompt manager into a single `respond` call:

    classify the moment  →  move the axes  →  recall memory  →
    assemble the two-segment prompt  →  voice the reply  →  remember

Two LLM calls per turn (classify, then voice) plus one embedding call when
memory is enabled. Purity over latency: the classifier never sees the axes and
the voicing model never sees the raw numbers.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.llm import LLMError, OllamaClient
from engine.memory import VectorStore
from engine.pack.models import CharacterPack
from engine.perception import TagClassifier
from engine.prompt_manager import DialogueTurn, PromptInputs, PromptManager
from engine.state import (
    DEFAULT_AXIS_MAX,
    Axes,
    StateKernel,
    relationship_ratio,
    resolve_stage,
)


@dataclass(frozen=True)
class TokenUsage:
    """Tokens spent on one turn (both the classify and voice calls)."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


@dataclass(frozen=True)
class TurnResult:
    """The outcome of one turn, ready for the API layer to project."""

    reply: str
    tag: str
    axes: Axes
    sprite: str | None
    stage: str | None
    stage_changed: bool
    usage: TokenUsage = TokenUsage()


class CharacterRuntime:
    """Runs turns for one character session (one pack, one evolving state)."""

    def __init__(
        self,
        pack: CharacterPack,
        llm: OllamaClient,
        *,
        state: StateKernel | None = None,
        memory: VectorStore | None = None,
        prompt_manager: PromptManager | None = None,
        classifier: TagClassifier | None = None,
        embed_model: str = "",
        recall_k: int = 3,
        axis_max: float = DEFAULT_AXIS_MAX,
    ) -> None:
        self._pack = pack
        self._llm = llm
        self._axis_max = axis_max
        self._state = state or StateKernel.from_pack(pack, axis_max=axis_max)
        self._memory = memory
        self._pm = prompt_manager or PromptManager()
        self._classifier = classifier or TagClassifier(llm)
        self._embed_model = embed_model
        self._recall_k = recall_k

    @property
    def state(self) -> StateKernel:
        return self._state

    def respond(
        self,
        user_message: str,
        dialogue_window: tuple[DialogueTurn, ...] = (),
    ) -> TurnResult:
        usage_before = self._usage_snapshot()

        tag = self._classifier.classify(self._pack, user_message, dialogue_window)

        pre_axes = self._state.axes
        axes = self._state.apply(self._pack.deltas[tag])
        stage_obj, stage_changed = self._resolve_stage(pre_axes, axes)
        stage = stage_obj.id if stage_obj else None

        recall_text, query_vec = self._recall(user_message)

        inputs = PromptInputs(
            identity=self._pack.identity,
            invariants="\n".join(self._pack.invariants),
            stage_block=stage_obj.block if stage_obj else "",
            steering_block=self._pack.blocks[tag],
            memory_recall=recall_text,
            dialogue_window=dialogue_window,
            user_message=user_message,
        )
        reply = self._llm.chat(self._pm.build_messages(inputs))

        self._remember(user_message, query_vec)
        return TurnResult(
            reply=reply,
            tag=tag,
            axes=axes,
            sprite=self._sprite_for(tag),
            stage=stage,
            stage_changed=stage_changed,
            usage=self._usage_delta(usage_before),
        )

    def _usage_snapshot(self) -> dict[str, int] | None:
        fn = getattr(self._llm, "usage_snapshot", None)
        return fn() if callable(fn) else None

    def _usage_delta(self, before: dict[str, int] | None) -> TokenUsage:
        """Tokens spent between `before` and now (this turn's classify+voice)."""
        if before is None:
            return TokenUsage()
        after = self._llm.usage_snapshot()
        prompt = after["prompt_tokens"] - before["prompt_tokens"]
        completion = after["completion_tokens"] - before["completion_tokens"]
        return TokenUsage(prompt, completion, prompt + completion)

    def _resolve_stage(self, pre_axes: Axes, post_axes: Axes):
        """Active stage after the turn, and whether the turn crossed into it."""
        stages = self._pack.stages
        pre = resolve_stage(relationship_ratio(pre_axes, self._axis_max), stages)
        post = resolve_stage(relationship_ratio(post_axes, self._axis_max), stages)
        pre_id = pre.id if pre else None
        post_id = post.id if post else None
        return post, pre_id != post_id

    def idle(self) -> Axes:
        """Apply one decay step (call between turns / after inactivity)."""
        return self._state.decay(self._pack.decay)

    # ---------------------------------------------------------------- memory

    def _recall(self, user_message: str) -> tuple[str, list[float] | None]:
        """Embed the message once; use it to search now and to store later."""
        if self._memory is None:
            return "", None
        try:
            vector = self._llm.embed(user_message, model=self._embed_model)
        except LLMError:
            return "", None
        hits = self._memory.search(vector, top_k=self._recall_k)
        return "\n".join(h.text for h in hits), vector

    def _remember(self, user_message: str, vector: list[float] | None) -> None:
        if self._memory is None or vector is None:
            return
        try:
            self._memory.add(
                user_message,
                vector,
                source="user",
                embedding_model=self._embed_model,
            )
        except ValueError:
            # A degenerate embedding should never sink a turn.
            pass

    # ---------------------------------------------------------------- sprite

    def _sprite_for(self, tag: str) -> str | None:
        sprites = self._pack.sprites
        return sprites.get(tag) or sprites.get("default")
