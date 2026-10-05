"""Pydantic models for a character pack.

These validate the *shape* of `pack.yaml` (types, ranges, cross-references,
balance rules). Filesystem/security concerns — YAML safety, sprite path
traversal, size limits, injection scanning — live in `loader.py`, which runs
before and after model validation.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

_NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"
_SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"

MIN_TAGS = 2
MAX_TAGS = 32
MAX_STAGES = 32


class PackMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_NAME_PATTERN)
    display_name: str = Field(min_length=1)
    version: str = Field(pattern=_SEMVER_PATTERN)
    license: str = Field(min_length=1)
    author: str = Field(min_length=1)
    fallback_tag: str = Field(pattern=_NAME_PATTERN)
    description: str = ""


class AxisConfig(BaseModel):
    """Per-axis configuration. Only the starting value is authored (in points);
    the ceiling is a runtime/env knob, not part of the character (see
    `AXIS_MAX` / slow-burn in the SPEC), and the floor is always 0."""

    model_config = ConfigDict(extra="forbid")

    start: float = Field(default=0.0, ge=0.0)


class AxesConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affection: AxisConfig = Field(default_factory=AxisConfig)
    trust: AxisConfig = Field(default_factory=AxisConfig)
    bond: AxisConfig = Field(default_factory=AxisConfig)


class GatedTag(BaseModel):
    """Mixin: an availability window on the closeness ratio (affection+trust,
    0..1). A tag is offered to the classifier only while the ratio is within
    `[unlock_at, lock_at]`; below or above, the engine simply never presents it,
    so the model *cannot* pick it. Ungated (`[0, 1]`) = always available.

    This is how reactions come and go with the relationship — e.g. a tag that
    accepts a romantic advance can be gated to a late stage, so the engine (not
    prompt prose) enforces that it isn't even an option before then."""

    unlock_at: float = Field(default=0.0, ge=0.0, le=1.0)
    lock_at: float = Field(default=1.0, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def _gate_window_ordered(self) -> GatedTag:
        if self.unlock_at > self.lock_at:
            raise ValueError(
                f"unlock_at ({self.unlock_at}) must be <= lock_at ({self.lock_at})"
            )
        return self

    def available_at(self, ratio: float) -> bool:
        return self.unlock_at <= ratio <= self.lock_at


class ActionBound(GatedTag):
    """What she will not do in the world — and from which stage she will.

    Tag gates decide WHAT she can feel; this one decides what she can DO. The difference is
    not cosmetic: a tag lives one turn, while a deed changes the world forever, and a killed
    villager is not taken back by a stage or a mood.

    The rule belongs to the pack, not the engine, for the same reason as `deltas` and `blocks`:
    the word `villager` is one world's vocabulary, and the engine is only meant to know "the pack
    named a limit, and the limit is enforced in code, not in a request to the model".

    `never` is not a window. A window says "too early yet"; `never` says "this one never
    will", and characters do have such things: in hardcore taking his food means killing him,
    and that is the one thing she will not do. They must not be mixed, or "never" turns out to
    be "after 0.99".
    """

    model_config = ConfigDict(extra="forbid")

    verb: str = Field(min_length=1)
    # What exactly. Empty — any item of this verb; a list — any of those listed.
    object: str | list[str] = ""
    never: bool = False
    # What she is told about it, in her own words. A refusal without a reason she reads as a
    # breakage and writes the same line again — that already happened with unread lines (03.09).
    refuse: str = Field(default="", min_length=0)

    @model_validator(mode="after")
    def _never_has_no_window(self) -> ActionBound:
        if self.never and (self.unlock_at > 0.0 or self.lock_at < 1.0):
            raise ValueError("a `never` bound cannot also carry a window")
        return self

    def names(self) -> tuple[str, ...]:
        if isinstance(self.object, str):
            return (self.object,) if self.object else ()
        return tuple(self.object)

    def covers(self, verb: str, objects: tuple[str, ...]) -> bool:
        """Whether the rule is about this deed."""
        if verb != self.verb:
            return False
        named = self.names()
        if not named:
            return True
        # `where.all` arrives as an empty item list, and that is NOT "nothing": taking everything
        # includes what is listed. Otherwise the limit is bypassed with one word.
        return not objects or any(one in named for one in objects)

    def allows(self, ratio: float) -> bool:
        return False if self.never else self.available_at(ratio)


class MomentTag(GatedTag):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_NAME_PATTERN)
    description: str = Field(min_length=1)
    sentiment: str = Field(default="neutral", pattern=r"^(positive|negative|neutral)$")


class DeltaVector(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affection: float = 0.0
    trust: float = 0.0
    bond: float = 0.0

    @model_validator(mode="after")
    def _bond_is_slow(self) -> DeltaVector:
        # Bond is the long-horizon axis: it may never move faster than the
        # per-message axes. Keeps a pack from turning bond into a fast lane.
        if abs(self.bond) > abs(self.affection) or abs(self.bond) > abs(self.trust):
            raise ValueError(
                "bond delta magnitude must be <= affection and trust deltas"
            )
        return self


class DecayConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    affection: float = Field(default=0.5, ge=0.0)
    trust: float = Field(default=0.3, ge=0.0)
    bond: float = Field(default=0.05, ge=0.0)


class Stage(BaseModel):
    """One author-defined relationship stage.

    Active while the closeness ratio (see engine.state.relationship_ratio) is
    at or below `up_to`. Thresholds are ratios in (0, 1], so they are
    independent of the axis ceiling — the same stages work at any `AXIS_MAX`,
    which is what makes slow-burn a pure deployment knob.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_NAME_PATTERN)
    up_to: float = Field(gt=0.0, le=1.0)
    block: str = ""


class LoopStep(BaseModel):
    """What she carries into the Nth world of a loop (see `Loop`)."""

    model_config = ConfigDict(extra="forbid")

    block: str = Field(min_length=1)


class Loop(BaseModel):
    """A story that outlives the world: a hidden counter of tries.

    A tag in `arm_on` arms it; the next time the host reports a DIFFERENT world
    (a new try), the counter steps and stays. From then on the step's block rides
    every turn — step N uses `steps[N-1]`, the last step covers the rest. The
    counter is never reported to a client and survives a relationship reset:
    only deleting the session's data clears it.
    """

    model_config = ConfigDict(extra="forbid")

    arm_on: list[str] = Field(min_length=1)
    steps: list[LoopStep] = Field(min_length=1, max_length=8)


class CharacterPack(BaseModel):
    """The fully validated character pack (shape-level)."""

    model_config = ConfigDict(extra="forbid")

    spec_version: int
    meta: PackMeta
    identity: str = Field(min_length=1)
    # Optional short reminder injected next to the user message every turn.
    # A nearby nudge (e.g. "be brief") is followed far better than a rule in
    # the far-away system prefix; leave empty when the invariants suffice.
    reply_directive: str = ""
    tags: list[MomentTag] = Field(min_length=MIN_TAGS, max_length=MAX_TAGS)
    deltas: dict[str, DeltaVector]
    blocks: dict[str, str]
    axes: AxesConfig = Field(default_factory=AxesConfig)
    # How many turns a deed of this kind holds in the dossier. A reference per tag, because
    # deeds have different terms: rudeness stops counting after a couple of dozen turns, a
    # killing does not. What is not listed lives `REMEMBERED_FOR` turns.
    #
    # It lives in the PACK, not the engine, for the same reason `deltas` and `blocks` live here:
    # tag names are the pack's vocabulary, and a table with the word `insult` inside a generic
    # engine would make it know one character's vocabulary.
    # Which axis stages and tag windows are read on. By default closeness, as for every pack
    # before this field; `bond` for an arc that must not turn back after one bad
    # evening.
    stage_axis: Literal["closeness", "bond"] = "closeness"
    remembered_for: dict[str, int] = Field(default_factory=dict)
    # Tags whose price falls with repetition: the N-th within its term is worth 1/N.
    # It keeps the relationship from being bought by quantity.
    diminishing: list[str] = Field(default_factory=list)
    sprites: dict[str, str] = Field(default_factory=dict)
    decay: DecayConfig = Field(default_factory=DecayConfig)
    stages: list[Stage] = Field(default_factory=list, max_length=MAX_STAGES)
    invariants: list[str] = Field(default_factory=list)
    actions: list[str] = Field(default_factory=list)
    # Limits of what she does with her HANDS. Empty — the pack forbids nothing, and the engine
    # decides nothing for it.
    bounds: list[ActionBound] = Field(default_factory=list)
    # Kinds of world notes this character does not get at all (`advanced`, `watched`…).
    # A story game does not see the game's mechanics: Mizuki, 27.09 — advancements turned into a
    # "vending machine" and a "factory" for her. Empty — sees everything, as all packs did before the field.
    unseen_notes: list[str] = Field(default_factory=list)
    # The loop: a hidden counter of attempts that outlives the world (Mizuki, 30.09). None — no loop.
    loop: Loop | None = None

    @model_validator(mode="after")
    def _cross_references(self) -> CharacterPack:
        tag_ids = [t.id for t in self.tags]
        tag_set = set(tag_ids)

        if len(tag_ids) != len(tag_set):
            raise ValueError("tag ids must be unique")

        # Every tag needs exactly one delta and one block; no orphans.
        if set(self.deltas) != tag_set:
            raise ValueError("deltas must cover exactly the declared tags")
        if set(self.blocks) != tag_set:
            raise ValueError("blocks must cover exactly the declared tags")

        for key in self.diminishing:
            if key not in tag_set:
                raise ValueError(f"diminishing names {key!r}, which is not a tag")

        # Memory terms — only for declared tags, and only positive ones.
        for key, turns in self.remembered_for.items():
            if key not in tag_set:
                raise ValueError(f"remembered_for names {key!r}, which is not a tag")
            if turns <= 0:
                raise ValueError(f"remembered_for[{key!r}] must be a positive number of turns")

        # Fallback tag must be a real tag.
        if self.meta.fallback_tag not in tag_set:
            raise ValueError(
                f"meta.fallback_tag {self.meta.fallback_tag!r} is not a declared tag"
            )

        # Sprite state keys must be 'default' or a known tag.
        for key in self.sprites:
            if key != "default" and key not in tag_set:
                raise ValueError(f"sprite state {key!r} is neither 'default' nor a tag")
        if self.sprites and "default" not in self.sprites:
            raise ValueError("sprites map must include a 'default' entry")

        # Balance: at least one negative tag (see SPEC §6).
        if not any(t.sentiment == "negative" for t in self.tags):
            raise ValueError("pack must declare at least one negative-sentiment tag")

        if self.loop is not None:
            for key in self.loop.arm_on:
                if key not in tag_set:
                    raise ValueError(f"loop.arm_on names {key!r}, which is not a tag")

        # Stages: unique ids, strictly ascending thresholds (author-defined,
        # any number).
        stage_ids = [s.id for s in self.stages]
        if len(stage_ids) != len(set(stage_ids)):
            raise ValueError("stage ids must be unique")
        ups = [s.up_to for s in self.stages]
        if any(ups[i] >= ups[i + 1] for i in range(len(ups) - 1)):
            raise ValueError("stage 'up_to' thresholds must be strictly ascending")

        return self

    def tag(self, tag_id: str) -> MomentTag:
        for t in self.tags:
            if t.id == tag_id:
                return t
        raise KeyError(tag_id)
