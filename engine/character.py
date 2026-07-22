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
from engine.web import WebResult, WebSearcher

# A turn classified with this tag triggers an (opt-in) web lookup, whose result
# snippets are handed to the voicing model as grounding. A pack must declare the
# tag for it to ever be chosen.
WEB_LOOKUP_TAG = "web_lookup"

NON_RP_RULE = (
    "Non-roleplay mode: reply only with spoken words, as a plain conversational "
    "assistant. Do not narrate, describe, or act out your gestures, expressions, "
    "movements, or the scene — no asterisk actions (like *smiles*) and no "
    "parenthetical stage directions. Keep your character's voice and personality, "
    "but answer directly, helpfully, and concisely."
)

NON_ROMANCE_RULE = (
    "Non-romance mode: keep the relationship strictly platonic no matter how "
    "close you grow. Do not flirt, express romantic or sexual interest, or steer "
    "the conversation toward romance. If the user makes a romantic advance, "
    "gently and kindly redirect toward friendship without shaming them. Warmth, "
    "care, and closeness as friends are welcome; romance is not."
)

# The user's grammatical gender, so a character addresses them correctly in
# languages that mark it (verb/adjective agreement, pronouns) — Russian, etc.
_USER_GENDER_RULE = {
    "male": (
        "The user is male. In any language that marks grammatical gender "
        "(pronouns, verb and adjective agreement), refer to and address the "
        "user using masculine forms."
    ),
    "female": (
        "The user is female. In any language that marks grammatical gender "
        "(pronouns, verb and adjective agreement), refer to and address the "
        "user using feminine forms."
    ),
}
_USER_GENDER_HINT = {"male": "(The user is male.)", "female": "(The user is female.)"}


def _language_rule(language: str) -> str:
    return f"Always write every reply in {language}, whatever language the user writes in."


def _language_hint(language: str) -> str:
    return f"(Write this reply in {language}.)"


# Per-turn reminders placed next to the user message. Small models follow a
# nearby reminder better than a single rule in the far-away system prefix.
_NON_RP_TAIL_HINT = "Answer in plain words only — no actions, emotes, or stage directions."
_NON_ROMANCE_TAIL_HINT = "Keep this platonic — warm as a friend, but no flirting or romance."


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
        non_rp: bool = False,
        non_romance: bool = False,
        language: str = "",
        user_gender: str = "",
        web_search: WebSearcher | None = None,
    ) -> None:
        self._pack = pack
        self._llm = llm
        self._axis_max = axis_max
        self._non_rp = non_rp
        self._non_romance = non_romance
        self._language = (language or "").strip()
        self._user_gender = (user_gender or "").strip().lower()
        self._web_search = web_search
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
            invariants=self._invariants(),
            stage_block=stage_obj.block if stage_obj else "",
            steering_block=self._steering_block(tag),
            memory_recall=recall_text,
            web_context=self._web_lookup(tag, user_message),
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

    def _invariants(self) -> str:
        """Pinned rules: the pack's invariants, plus any enabled mode rules."""
        rules = list(self._pack.invariants)
        if self._non_rp:
            rules.append(NON_RP_RULE)
        if self._non_romance:
            rules.append(NON_ROMANCE_RULE)
        if self._language:
            rules.append(_language_rule(self._language))
        if self._user_gender in _USER_GENDER_RULE:
            rules.append(_USER_GENDER_RULE[self._user_gender])
        return "\n".join(rules)

    def _web_lookup(self, tag: str, query: str) -> str:
        """Run an opt-in web search when this turn asked for a lookup."""
        if tag != WEB_LOOKUP_TAG or self._web_search is None:
            return ""
        results = self._web_search.search(query)
        return _format_web_results(results)

    def _steering_block(self, tag: str) -> str:
        """This turn's tag block, plus the pack's per-turn reminder and any
        enabled mode reminders — placed near the user message where a small
        model heeds them best."""
        parts = [self._pack.blocks[tag], self._pack.reply_directive]
        if self._non_rp:
            parts.append(_NON_RP_TAIL_HINT)
        if self._non_romance:
            parts.append(_NON_ROMANCE_TAIL_HINT)
        if self._language:
            parts.append(_language_hint(self._language))
        if self._user_gender in _USER_GENDER_HINT:
            parts.append(_USER_GENDER_HINT[self._user_gender])
        return "\n".join(p for p in parts if p).strip()

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


def _format_web_results(results: list[WebResult]) -> str:
    """Compact grounding text from search hits (empty when none)."""
    lines = [f"- {r.title}: {r.snippet} ({r.url})".strip() for r in results if r.title]
    return "\n".join(lines)
