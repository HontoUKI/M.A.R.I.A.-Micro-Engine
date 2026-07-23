"""Scene runtime — one group-chat turn, end to end.

Composes the cast (character packs), the relationship matrix, the director
(speaker selection) and the moment classifier into a single `advance` call:

    pick the speaker  ->  classify (tag, target)  ->  voice the acting actor
    with the scene's setting and their tone toward the target  ->  move the
    speaker's edge toward the target

The witness pass (bystanders reacting to what they saw) lands in a later stage;
this stage moves only the speaking actor's own edge.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine.llm import LLMError, OllamaClient
from engine.pack.models import CharacterPack, DeltaVector
from engine.prompt_manager import DialogueTurn, PromptInputs, PromptManager
from engine.scene.director import SpeakerSelector, next_round_robin
from engine.scene.matrix import RelationshipMatrix
from engine.scene.models import USER_ID, ScenePack
from engine.scene.tags import ActorTagset, SceneTag
from engine.state import DEFAULT_AXIS_MAX, Axes, relationship_ratio, resolve_stage
from engine.textjson import loads_lenient

# How the user shows up in the cast presence line and dialogue window.
_USER_LABEL = "User"
# In play mode the user's lines are narrator cues, recorded under this speaker id
# so they read as stage directions and are never a target actors address.
NARRATOR = "narrator"


@dataclass(frozen=True)
class SceneLine:
    """One spoken line in the shared scene transcript."""

    speaker: str  # an actor id, or USER_ID
    content: str


@dataclass(frozen=True)
class WitnessReaction:
    """How a bystander's feelings shifted from watching the turn (no spoken
    line — witnessing only moves state)."""

    actor: str
    tag: str
    target: str
    feeling: Axes


@dataclass(frozen=True)
class SceneTurnResult:
    """The outcome of one scene turn."""

    speaker: str
    reply: str
    tag: str
    target: str
    feeling: Axes  # the speaker's feeling toward the target after the turn
    witnessed: tuple[WitnessReaction, ...] = ()


@dataclass
class SceneRuntime:
    """Runs turns for one loaded scene (a cast, a matrix, a shared transcript)."""

    scene: ScenePack
    packs: dict[str, CharacterPack]
    llm: OllamaClient
    matrix: RelationshipMatrix = None  # type: ignore[assignment]
    prompt_manager: PromptManager = None  # type: ignore[assignment]
    selector: SpeakerSelector = None  # type: ignore[assignment]
    axis_max: float = DEFAULT_AXIS_MAX
    max_retries: int = 1
    # Witnessing an exchange moves a bystander's feelings less than being in it.
    witness_scale: float = 0.5
    transcript: list[SceneLine] = field(default_factory=list)

    def __post_init__(self) -> None:
        missing = [a for a in self.scene.cast if a not in self.packs]
        if missing:
            raise KeyError(f"scene cast not loaded: {missing}")
        if self.matrix is None:
            self.matrix = RelationshipMatrix.from_scene(self.scene, axis_max=self.axis_max)
        if self.prompt_manager is None:
            self.prompt_manager = PromptManager()
        if self.selector is None:
            self.selector = SpeakerSelector(self.llm, max_retries=self.max_retries)
        # Build each actor's merged tag vocabulary (base + scenario), which also
        # runs the deferred base-vs-scenario id collision check.
        self._tagsets: dict[str, ActorTagset] = {
            actor: ActorTagset.build(self.packs[actor], self.scene.scenario_tags.get(actor))
            for actor in self.scene.cast
        }
        self._last_speaker: str | None = None

    # ------------------------------------------------------------------ turn

    def advance(
        self, user_message: str | None = None, *, speaker: str | None = None
    ) -> SceneTurnResult:
        """One group-chat turn: the user speaks as a participant.

        A caller (or the director) may name the `speaker`, otherwise the director
        picks and round-robin is the fallback.
        """
        if user_message is not None:
            self.transcript.append(SceneLine(USER_ID, user_message))
        actor = self._resolve_speaker(speaker, user_message or "")
        return self._take_turn(actor)

    def run(
        self, cue: str | None = None, *, max_turns: int = 1
    ) -> list[SceneTurnResult]:
        """Play/narrator turns: the user feeds a `cue` (a stage direction the
        cast reacts to but never answers) and the cast acts among themselves for
        up to `max_turns`, the director choosing each speaker."""
        if cue:
            self.transcript.append(SceneLine(NARRATOR, cue))
        results: list[SceneTurnResult] = []
        for _ in range(max(1, max_turns)):
            actor = self._resolve_speaker(None, self._trigger_text())
            results.append(self._take_turn(actor))
        return results

    def _take_turn(self, actor: str) -> SceneTurnResult:
        """One actor's turn: classify the moment, voice it, move the edge, then
        run the witness pass. Shared by group chat and play mode."""
        pack = self.packs[actor]
        tagset = self._tagsets[actor]
        targets = self._targets_for(actor)
        available = tagset.available(self._scene_ratio(actor))

        tag_id, target = self._classify_moment(actor, available, targets)
        tag = tagset.get(tag_id)

        reply = self.llm.chat(self._build_messages(actor, pack, tag, target))
        self.matrix.apply(actor, target, tag.delta)
        self.transcript.append(SceneLine(actor, reply))
        self._last_speaker = actor

        witnessed = self._witness_pass(actor)
        return SceneTurnResult(
            speaker=actor,
            reply=reply,
            tag=tag_id,
            target=target,
            feeling=self.matrix.feeling(actor, target),
            witnessed=witnessed,
        )

    def _targets_for(self, actor: str) -> list[str]:
        """Who this actor's reaction can be about. In play mode the user is the
        narrator, not a participant, so actors address each other — never the
        user."""
        parts = [p for p in self._participants() if p != actor]
        if self.scene.mode == "play":
            parts = [p for p in parts if p != USER_ID]
        return parts

    def _scene_ratio(self, actor: str) -> float:
        """The "how far the story has come for me" anchor that gates an actor's
        tags: their standing toward the user in group chat, or their strongest
        bond to anyone in play mode (where there is no user in the cast)."""
        if self.scene.mode == "play":
            ratios = [
                relationship_ratio(self.matrix.feeling(actor, p), self.axis_max)
                for p in self._participants()
                if p != actor and p != USER_ID
            ]
            return max(ratios, default=0.0)
        return relationship_ratio(self.matrix.feeling(actor, USER_ID), self.axis_max)

    # -------------------------------------------------------------- witness

    def _witness_pass(self, speaker: str) -> tuple[WitnessReaction, ...]:
        """Every bystander reacts to what they just saw — their edge toward the
        participant the moment is about moves, scaled down (watching lands softer
        than taking part). Bystanders don't speak; witnessing only moves state.
        """
        reactions: list[WitnessReaction] = []
        for actor in self.scene.cast:
            if actor == speaker:
                continue
            targets = self._targets_for(actor)
            available = self._tagsets[actor].available(self._scene_ratio(actor))
            tag_id, target = self._classify_moment(actor, available, targets)
            tag = self._tagsets[actor].get(tag_id)
            self.matrix.apply(actor, target, _scaled(tag.delta, self.witness_scale))
            reactions.append(
                WitnessReaction(
                    actor=actor,
                    tag=tag_id,
                    target=target,
                    feeling=self.matrix.feeling(actor, target),
                )
            )
        return tuple(reactions)

    # -------------------------------------------------------------- speaker

    def _resolve_speaker(self, explicit: str | None, trigger: str) -> str:
        if explicit is not None:
            if explicit not in self.scene.cast:
                raise ValueError(f"{explicit!r} is not in the cast")
            return explicit
        if self.scene.director == "model":
            picked = self.selector.choose(
                self.scene.cast,
                self._transcript_text(limit=6),
                trigger,
                descriptions={a: self.packs[a].meta.description for a in self.scene.cast},
            )
            if picked is not None:
                return picked
        return next_round_robin(self.scene.cast, self._last_speaker)

    # ----------------------------------------------------------- perception

    def _classify_moment(
        self, actor: str, available: list[SceneTag], targets: list[str]
    ) -> tuple[str, str]:
        """Pick the moment tag AND who it is about (which matrix edge moves)."""
        fallback_tag = self._tagsets[actor].fallback
        fallback_target = USER_ID if USER_ID in targets else targets[0]
        schema = {
            "type": "object",
            "properties": {
                "tag": {"type": "string", "enum": [t.id for t in available]},
                "target": {"type": "string", "enum": targets},
            },
            "required": ["tag", "target"],
        }
        messages = self._moment_messages(actor, available, targets)
        valid_tags = {t.id for t in available}
        for _ in range(self.max_retries + 1):
            try:
                raw = self.llm.chat(messages, fmt=schema, options={"temperature": 0.0})
            except LLMError:
                break
            parsed = _parse_moment(raw)
            # A valid tag is the load-bearing signal; if the target is off, keep
            # the tag and default the target rather than discarding both.
            if parsed and parsed[0] in valid_tags:
                target = parsed[1] if parsed[1] in targets else fallback_target
                return parsed[0], target
        return fallback_tag, fallback_target

    def _moment_messages(
        self, actor: str, available: list[SceneTag], targets: list[str]
    ) -> list[dict[str, str]]:
        display = self._display(actor)
        lines = [
            f"You classify moments in a group scene, for the character {display}.",
            "Read the conversation, then classify the LATEST line only: pick the "
            "one tag that best captures what that line expresses, and the "
            "participant it is directed at or about (the target).",
            "Judge what the line itself conveys, NOT how composed or guarded "
            f"{display} is. A warm or hostile line is warm or hostile even if "
            f"{display} would answer it coolly. Choose 'neutral' ONLY when no "
            "other tag genuinely fits — prefer a specific tag whenever one does.",
            'Respond only as JSON of the form {"tag": "<id>", "target": "<id>"}.',
            "Tags:",
        ]
        lines.extend(f"- {t.id}: {t.description}" for t in available)
        lines.append(
            "Targets (who the line is directed at or about): "
            + ", ".join(f"{self._display(p)}={p}" for p in targets)
        )
        messages: list[dict[str, str]] = [{"role": "system", "content": "\n".join(lines)}]
        # Prior lines as context, then the latest line as a clean final message so
        # the model classifies IT, not the whole history.
        messages.extend(self._window_for(actor, drop_last=True))
        messages.append({"role": "user", "content": "Latest line — " + self._trigger_line(actor)})
        return messages

    # -------------------------------------------------------------- voicing

    def _build_messages(
        self, actor: str, pack: CharacterPack, tag: SceneTag, target: str
    ) -> list[dict[str, str]]:
        edge_ratio = relationship_ratio(self.matrix.feeling(actor, target), self.axis_max)
        stage = resolve_stage(edge_ratio, pack.stages)
        tone = ""
        if stage is not None:
            tone = f"Toward {self._display(target)} right now: {stage.block.strip()}"

        window = self._window_for(actor, drop_last=True)
        trigger = self._trigger_line(actor)
        invariants = list(pack.invariants)
        if self.scene.mode == "play":
            invariants.append(
                "You are acting out a scene. A line in [Scene: ...] is a stage "
                "direction describing what is happening — react to the event and "
                "speak to the other characters, but never address or answer a "
                "narrator or the audience."
            )
        inputs = PromptInputs(
            identity=self._identity(actor, pack),
            invariants="\n".join(invariants),
            stage_block=tone,
            steering_block=tag.block,
            dialogue_window=tuple(DialogueTurn(m["role"], m["content"]) for m in window),
            user_message=trigger,
        )
        return self.prompt_manager.build_messages(inputs)

    def _identity(self, actor: str, pack: CharacterPack) -> str:
        # In play mode the user is the narrator, not on stage — only other actors.
        onstage = [a for a in self.scene.cast if a != actor]
        if self.scene.mode != "play":
            onstage.append(USER_ID)
        others = [self._display(p) for p in onstage]
        presence = "On stage with you: " + ", ".join(others) + "." if others else ""
        parts = [pack.identity.strip()]
        if self.scene.setting.strip():
            parts.append("The scene:\n" + self.scene.setting.strip())
        if presence:
            parts.append(presence)
        return "\n\n".join(parts)

    # --------------------------------------------------------------- shared

    def _participants(self) -> list[str]:
        return [*self.scene.cast, USER_ID]

    def _display(self, participant: str) -> str:
        if participant == USER_ID:
            return _USER_LABEL
        if participant == NARRATOR:
            return "Narrator"
        return self.packs[participant].meta.display_name

    def _label(self, line: SceneLine) -> str:
        """A transcript line as one labeled string. A narrator cue reads as a
        stage direction so actors react to the event, not to a speaker."""
        if line.speaker == NARRATOR:
            return f"[Scene: {line.content}]"
        return f"{self._display(line.speaker)}: {line.content}"

    def _window_for(self, actor: str, *, drop_last: bool) -> list[dict[str, str]]:
        """Recent transcript from `actor`'s POV: own lines are 'assistant', all
        others are 'user' — labeled with the speaker, or as a [Scene: ...] cue."""
        lines = self.transcript[:-1] if drop_last and self.transcript else self.transcript
        out: list[dict[str, str]] = []
        for line in lines:
            if line.speaker == actor:
                out.append({"role": "assistant", "content": line.content})
            else:
                out.append({"role": "user", "content": self._label(line)})
        return out

    def _trigger_line(self, actor: str) -> str:
        if not self.transcript:
            return ""
        last = self.transcript[-1]
        if last.speaker == actor:  # shouldn't happen, but stay safe
            return last.content
        return self._label(last)

    def _trigger_text(self) -> str:
        return self._label(self.transcript[-1]) if self.transcript else ""

    def _transcript_text(self, *, limit: int) -> str:
        return "\n".join(self._label(line) for line in self.transcript[-limit:])


def _parse_moment(raw: str) -> tuple[str, str] | None:
    data = loads_lenient(raw)
    if not isinstance(data, dict):
        return None
    tag, target = data.get("tag"), data.get("target")
    if isinstance(tag, str) and isinstance(target, str):
        return tag, target
    return None


def _scaled(delta: DeltaVector, scale: float) -> DeltaVector:
    """A delta scaled by `scale`. Scaling preserves the bond<=affection/trust
    invariant, so the result is always a valid delta."""
    return DeltaVector(
        affection=delta.affection * scale,
        trust=delta.trust * scale,
        bond=delta.bond * scale,
    )
