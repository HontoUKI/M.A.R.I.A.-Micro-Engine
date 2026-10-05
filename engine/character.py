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

from dataclasses import dataclass, replace

from engine.action_history import ActionHistory
from engine.dossier import summarise, worth
from engine.glossary import LOOKUP, GlossaryNotes
from engine.hands import (
    GameActionNotCompleted,
    GamePort,
    GameRequestRejected,
    describe,
    read_intention,
    require_game_acceptance,
)
from engine.llm import LLMError, OllamaClient
from engine.memory import VectorStore
from engine.pack.models import CharacterPack
from engine.perception import TagClassifier
from engine.prompt_manager import DialogueTurn, PromptInputs, PromptManager
from engine.state import (
    DEFAULT_AXIS_MAX,
    Axes,
    StateKernel,
    resolve_stage,
    scaled,
    standing_ratio,
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

GAMER_RULE = (
    "Game mode: you are inside a game world, and the only things in it are what the notes "
    "from the world and the player's words have shown you. Never invent objects, machines, "
    "sounds, creatures, places, people or events you have not been shown, and never claim to "
    "see, hear, hold or have done something the notes do not show. When you do not know "
    "what is around or what happened, say so or ask."
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
_GAMER_TAIL_HINT = (
    "Only what the notes and the player's words showed you is there — invent nothing."
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
    # What she set going in the world this turn, in the game's own words. Empty
    # when no game is attached or when she chose to do nothing — which is a
    # choice, and one the block in the prompt says out loud she may make.
    did: tuple[str, ...] = ()
    # Internal game-loop wake: there may be no router event for an unread call.
    game_feedback_pending: bool = False


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
        gamer: bool = False,
        non_romance: bool = False,
        language: str = "",
        user_gender: str = "",
        web_search: WebSearcher | None = None,
        hands: GamePort | None = None,
        deeds: tuple = (),
        mentioned: str = "",
        loop_block: str = "",
        glossary_notes: GlossaryNotes | None = None,
        action_history: ActionHistory | None = None,
    ) -> None:
        self._pack = pack
        self._llm = llm
        self._axis_max = axis_max
        self._non_rp = non_rp
        self._gamer = gamer
        self._non_romance = non_romance
        self._language = (language or "").strip()
        self._user_gender = (user_gender or "").strip().lower()
        self._web_search = web_search
        # A pack cannot turn this on: whether a game is attached is a deployment
        # decision, like the choice of model. See engine/hands.py.
        self._hands = hands
        self._glossary = glossary_notes if glossary_notes is not None else GlossaryNotes()
        self._actions = action_history if action_history is not None else ActionHistory()
        self._lookup_blocked = False
        self._deeds = tuple(deeds)
        self._mentioned = mentioned
        # The step of the pack's loop she is on (engine/loop.py); empty outside one.
        self._loop_block = loop_block
        # The attempt she is part-way through, if any. Read when the world is
        # described and used when she answers, so "CONTINUE" means the thing she
        # was actually told about rather than whatever is open by then.
        self._paused: str = ""
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
        self._glossary.begin_turn()
        self._actions.begin_turn()

        # Gate the classifier's choices by the relationship *before* this turn:
        # a tag only unlocks once the standing is inside its window.
        # Tag gates are read on the same axis as stages: "what is available to her at all" is
        # a question of who he is to her, not of her mood today.
        ratio = self._standing(self._state.axes)
        tag = self._classifier.classify(
            self._pack, user_message, dialogue_window, ratio=ratio
        )

        pre_axes = self._state.axes
        # A deed's price falls with repetition if the pack says so: the N-th gift within its
        # term is worth 1/N. The dossier counts — it keeps this count anyway.
        axes = self._state.apply(
            scaled(self._pack.deltas[tag], worth(self._deeds, self._pack, tag))
        )
        stage_obj, stage_changed = self._resolve_stage(pre_axes, axes)
        stage = stage_obj.id if stage_obj else None

        recall_text, query_vec = self._recall(user_message)

        inputs = PromptInputs(
            identity=self._pack.identity,
            invariants=self._invariants(),
            stage_block="\n\n".join(
                part for part in (stage_obj.block if stage_obj else "", self._loop_block) if part
            ),
            steering_block=self._steering_block(tag),
            memory_recall=recall_text,
            web_context=self._web_lookup(tag, user_message),
            game_block=self._game_block(),
            dialogue_window=dialogue_window,
            user_message=user_message,
        )
        reply = self._llm.chat(self._pm.build_messages(inputs))
        request = LOOKUP.search(reply)
        if request is not None and self._hands is not None and not self._lookup_blocked:
            article = {"name": "Lookup", "index": True,
                       "text": "The glossary did not answer. Do not invent its contents."}
            try:
                article = self._hands.glossary(request.group(1))
                self._glossary.remember(article)
            except Exception:
                pass
            # No first-pass play is executed. Exactly one continuation, even if the
            # model emits another lookup; both the lookup and discarded play stay private.
            reference = (f"\n\nReference: {article['name']}\n{article['text']}\n"
                         "Answer the original turn now. No further lookup this turn.")
            continuation = replace(inputs, user_message=user_message + reference)
            reply = self._llm.chat(self._pm.build_messages(continuation))
        leftover_lookup = bool(LOOKUP.search(reply))
        reply = LOOKUP.sub("", reply).strip()
        reply, did = self._reach_for_the_game(reply)
        if (leftover_lookup and self._hands is not None
                and not getattr(self, "_lookup_blocked", False)):
            self._unread = getattr(self, "_unread", ()) + (
                "An additional lookup in your final response was not processed. "
                "Only one lookup is allowed per turn; request the next article on a later turn. "
                "The action calls in the final response were handled separately.",
            )

        self._remember(user_message, query_vec)
        return TurnResult(
            reply=reply,
            tag=tag,
            axes=axes,
            sprite=self._sprite_for(tag),
            stage=stage,
            stage_changed=stage_changed,
            usage=self._usage_delta(usage_before),
            did=did,
            game_feedback_pending=bool(
                getattr(self, "_unread", ()) or getattr(self, "_game_delivery_issue", "")
            ),
        )

    def _game_block(self) -> str:
        """What the world looks like this turn, or nothing at all.

        A router that has stopped answering means no block — not a stale one and
        not an empty heading. "There is a game and nothing to do in it" is a lie
        of exactly the kind that gets answered confidently.
        """
        if self._hands is None:
            return ""
        try:
            history = self._hands.history()
            sight = self._hands.sight()
            actions = getattr(self, '_actions', None)
            if actions is None:
                actions = self._actions = ActionHistory()
            actions.observe(sight.get('actions') or {})
            self._lookup_blocked = bool(sight.get("defending") or sight.get("mending"))
            self._paused = _paused_id(sight)
            # The unfinished wish: what she was going for and what is left. Kept apart from
            # the pause, because these are different things — interrupted work is continued from
            # the same place, a stopped one is raised again after a detour (§21).
            self._unfinished = sight.get("unfinished") or None
            block = describe(
                self._hands.offer(),
                sight,
                actions.render(
                    sight.get('ammunition'), sight.get('her', {}).get('effects'),
                    sight.get('equipment'),
                ),
                _paused_name(history, self._paused),
                self._unfinished,
                self._glossary.render(),
                effects_in_actions=sight.get('her', {}).get('effects') is not None,
            )
            held = getattr(self, "_held_back", ())
            if held:
                # Said once and removed: it is about the line she has just written, and a
                # complaint that outlives its turn becomes noise about the past.
                self._held_back = ()
                block = (
                    "You did not do this, and it was not the world that"
                    " stopped you: " + "; ".join(held) + "\n\n" + block
                )
            unread = getattr(self, "_unread", ())
            if unread:
                # Said once and cleared: it is about the line she just wrote, and a
                # complaint that outlives its turn becomes noise about the past.
                self._unread = ()
                block = (
                    "What you wrote in <play> last time could not be read, so "
                    "nothing moved: " + "; ".join(unread)
                    + "\nKnown routines use run(name, param: value); "
                    "primitive verbs use verb(arguments). "
                    "Do not write run name(arguments). Read lookup for the call's parameters."
                    + "\n\n" + block
                )
            delivery = getattr(self, "_game_delivery_issue", "")
            if delivery:
                self._game_delivery_issue = ""
                block = delivery + "\n\n" + block
            return block
        except Exception:
            return ""

    def _reach_for_the_game(self, reply: str) -> tuple[str, tuple[str, ...]]:
        """Cut her decision out of the reply and set it going.

        Parsed here, where it is read, so a decision cannot be spoken aloud as
        speech or reach a client as words. With no game attached the lines are
        still cut — a character who narrates her play at somebody is worse than one
        who cannot act. The block is read by the game (`GamePort.read`), which owns
        its language (28.09).
        """
        try:
            intention, speech = read_intention(
                reply, self._hands.read if self._hands is not None else None
            )
        except Exception:
            # The game did not answer: nothing moved, and the block is still not speech.
            intention, speech = read_intention(reply)
            self._game_delivery_issue = (
                "The game reader did not answer last time. Your calls were not sent for execution. "
                "This is a connection failure, not a syntax error or a refusal by the world."
            )
        # She is told next turn that a line of hers could not be read. Without this she
        # cannot tell "I acted" from "nothing happened", and on 03.09 she wrote the same
        # malformed line twice running — the world had no answer to give, because the
        # line never reached it.
        self._unread = intention.unread
        if not intention:
            # `speech`, never `reply`. An intention is falsy exactly when her play
            # was there and could not be READ — and that was the one path that put the
            # raw text back, so the protocol went out in the game chat verbatim. Live
            # 03.09 she answered a player with `DO: gather "cobblestone" 3 "search": 5`
            # twice running, having done nothing either time. The stripping in
            # `read_intention` is unconditional; the leak was here, one line under a
            # docstring that says the lines are always cut.
            return speech, ()
        if self._hands is None:
            return speech, ()
        try:
            # Going back to something takes priority over starting something new: a
            # turn that says both meant the first, and taking a goal would silently
            # abandon what she just said she wanted to finish.
            if intention.carry_on and self._paused:
                require_game_acceptance(self._hands.resume(self._paused))
                return speech, ("continue",)
            # The Router owns the difference between resuming a paused attempt
            # and starting the remaining steps of an unfinished plan.
            unfinished = getattr(self, "_unfinished", None)
            if intention.carry_on and unfinished:
                require_game_acceptance(self._hands.resume_plan(unfinished.get("plan", "")))
                return speech, ("continue",)
            if intention.let_go:
                if self._paused:
                    require_game_acceptance(self._hands.abandon(self._paused), release=True)
                if unfinished:
                    require_game_acceptance(
                        self._hands.abandon_plan(unfinished["plan"]), release=True
                    )
                if not intention.steps:
                    return speech, ("drop",)
            if not intention.steps:
                return speech, ()
            intention, held = self._within_bounds(intention)
            self._held_back = held
            if not intention.steps:
                return speech, ()
            require_game_acceptance(self._hands.act(intention))
        except GameRequestRejected as refusal:
            self._game_delivery_issue = (
                "The Router explicitly refused your last request; do not claim it succeeded. "
                "This is a confirmed request refusal, not a lost response. "
                "Current work may still be active; inspect it before replacing or repeating it. "
                + str(refusal)
            )
            return speech, ()
        except GameActionNotCompleted as outcome:
            self._game_delivery_issue = (
                "The Router returned a closed action without confirming completion. "
                "This is an action outcome, not a connection failure. Do not claim success "
                "or repeat a spending request without checking state and its confirmation. "
                + str(outcome)
            )
            return speech, ()
        except Exception:
            # A request may reach the game before its response is lost. Do not say
            # nothing happened, or encourage spending the same resources twice.
            self._game_delivery_issue = (
                "The game did not confirm your last action request. It may have been accepted; "
                "check current state and recent attempts before repeating it. "
                "This is a connection failure, not a confirmed refusal by the world."
            )
            return speech, ()
        said = tuple(
            f"{goal.verb} " + " ".join(f"{k}={v}" for k, v in goal.fields.items())
            if goal.fields
            else goal.verb
            for goal in intention.steps
        )
        return speech, said * 1 if intention.repeat == 1 else said + (f"x{intention.repeat}",)

    def _within_bounds(self, intention):
        """Remove from the decision what this character does not do.

        Tag gates decide what she can feel; this decides what she can DO. The difference is not
        cosmetic: a tag lives one turn, while a deed changes the world forever, and a killed
        villager is not taken back by a stage or a mood.

        It is held in CODE, not in a request to the model, for exactly the reason tag windows are
        held in code: the request "do not take his food" is honoured while the model remembers it,
        and it forgets at the most interesting moment. The pack names the limit, the engine
        enforces it.

        The refusal must be told to HER. A silently dropped step she reads as a breakage and
        writes the same line again — that already happened with unread lines (03.09).
        """
        bounds = getattr(self._pack, "bounds", None) or ()
        if not bounds:
            return intention, ()

        ratio = self._standing(self._state.axes)
        kept, held = [], []
        for goal in intention.steps:
            objects = _objects_of(goal)
            spared = _left_out(goal)
            stop = next(
                (
                    b for b in bounds
                    if b.covers(goal.verb, objects)
                    and not (b.names() and set(b.names()) <= spared)
                    and not b.allows(ratio)
                ),
                None,
            )
            if stop is None:
                kept.append(goal)
                continue
            named = " ".join(objects) or goal.verb
            said = f"{goal.verb} {named}"
            if stop.refuse:
                said = f"{said}: {stop.refuse}".strip()
            if _selects(goal) and stop.names():
                # A selection (`ALL where …`) names no things, and the engine does not know what
                # will fall into it — the vocabulary is the game's. The narrow way out: leave the forbidden behind EXCEPT.
                spared = ", ".join(stop.names())
                said += f" (a selection could include {spared} — leave it out with EXCEPT)"
            held.append(said)
        if len(kept) == len(intention.steps):
            return intention, ()
        return replace(intention, steps=tuple(kept)), tuple(held)

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
        if self._gamer:
            rules.append(GAMER_RULE)
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
        # The dossier goes FIRST: it is about what already happened, and this turn's occasion is
        # read against it, not the other way round.
        # What has already been said between them — next to the dossier: both are about the past,
        # not about this turn (engine/mentioned.py).
        parts = [
            summarise(self._deeds),
            self._mentioned,
            self._pack.blocks[tag],
            self._pack.reply_directive,
        ]
        if self._non_rp:
            parts.append(_NON_RP_TAIL_HINT)
        if self._gamer:
            parts.append(_GAMER_TAIL_HINT)
        if self._non_romance:
            parts.append(_NON_ROMANCE_TAIL_HINT)
        if self._language:
            parts.append(_language_hint(self._language))
        if self._user_gender in _USER_GENDER_HINT:
            parts.append(_USER_GENDER_HINT[self._user_gender])
        return "\n".join(p for p in parts if p).strip()

    def _standing(self, axes: Axes) -> float:
        """The share stages and tag windows are read by — on the axis the pack chose."""
        return standing_ratio(axes, self._axis_max, self._pack.stage_axis)

    def _resolve_stage(self, pre_axes: Axes, post_axes: Axes):
        """Active stage after the turn, and whether the turn crossed into it."""
        stages = self._pack.stages
        pre = resolve_stage(self._standing(pre_axes), stages)
        post = resolve_stage(self._standing(post_axes), stages)
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

def _selects(goal) -> bool:
    where = (goal.fields or {}).get("where")
    return isinstance(where, dict) and isinstance(where.get("select"), dict)


def _left_out(goal) -> set[str]:
    """What a selection leaves out by name (`EXCEPT [bread]`), as she wrote it."""
    if not _selects(goal):
        return set()
    return {str(w) for w in goal.fields["where"]["select"].get("except") or []}


def _objects_of(goal) -> tuple[str, ...]:
    """What a step names: the item itself and a list, if there is one.

    `where.all` — "take everything" — gives not a single name, and that is not "nothing": it
    includes what is listed in the limit. Emptiness here means "everything", and `covers` decides.
    """
    fields = goal.fields or {}
    where = fields.get("where") or {}
    # A selection (`ALL`/`FIRST … where …`, 28.09) is "everything" too: what falls into it the
    # world decides at the moment of the step, not the names in the line.
    if isinstance(where, dict) and (where.get("all") is True or _selects(goal)):
        return ()
    named = []
    one = fields.get("object")
    if isinstance(one, str) and one:
        named.append(one)
    items = where.get("items") if isinstance(where, dict) else None
    if isinstance(items, list):
        named.extend(str(i) for i in items if i)
    return tuple(named)


def _paused_id(sight: dict) -> str:
    """The attempt she stopped part-way through, if she is standing in one."""
    return str(sight.get("attempt") or "") if sight.get("paused") else ""


def _paused_name(history: list[dict], attempt_id: str) -> str:
    """What that attempt was, in the game's own words."""
    if not attempt_id:
        return ""
    for attempt in history or []:
        if attempt.get("id") == attempt_id:
            goal = attempt.get("goal") or {}
            what = goal.get("object")
            return f"{goal.get('verb')}" + (f" {what}" if isinstance(what, str) else "")
    return "something"
