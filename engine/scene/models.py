"""Pydantic models for a ScenePack — a "production" that casts Character Packs.

A ScenePack never edits a character; it *composes* several of them: it names the
cast, pins a shared setting, optionally seeds the relationship matrix with
starting feelings, and can grant scenario-only tags that layer onto specific
actors for the duration of the scene. See `docs/DESIGN_v0.2_SCENES.md`.

This validates the *shape* of `scene.yaml`. Filesystem/security concerns (YAML
safety, size limits, injection scanning) live in `loader.py`. Cross-references
that need the actual Character Packs (e.g. a scenario tag id must not collide
with a base tag) are checked later, at scene assembly, where the cast is loaded.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, model_validator

from engine.pack.models import DeltaVector, GatedTag

_NAME_PATTERN = r"^[a-z0-9][a-z0-9_-]*$"
_SEMVER_PATTERN = r"^\d+\.\d+\.\d+$"

# Reserved participant id for the human in the matrix. Not a valid pack name
# (the name pattern forbids nothing here, but the cast is character packs and
# the loader rejects "user" as a cast member to avoid the clash).
USER_ID = "user"

MIN_CAST = 1
MAX_CAST = 8
MAX_SCENARIO_TAGS_PER_ACTOR = 16


class SceneMeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern=_NAME_PATTERN)
    display_name: str = Field(min_length=1)
    version: str = Field(pattern=_SEMVER_PATTERN)
    license: str = Field(min_length=1)
    author: str = Field(min_length=1)
    description: str = ""


class RelationshipSeed(BaseModel):
    """A starting feeling on one directed edge of the matrix (from → to).

    Absolute starting points (not deltas), so a scene can open mid-story with an
    established crush or rivalry. `from`/`to` are cast member ids or `user`."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    affection: float = Field(default=0.0, ge=0.0)
    trust: float = Field(default=0.0, ge=0.0)
    bond: float = Field(default=0.0, ge=0.0)

    @model_validator(mode="after")
    def _no_self_edge(self) -> RelationshipSeed:
        if self.from_ == self.to:
            raise ValueError(f"relationship edge cannot point at itself ({self.from_})")
        return self


class ScenarioTag(GatedTag):
    """A moment-tag the *setting* grants one actor, layered on its base tags for
    this scene only. Self-contained: description (for the classifier), delta (how
    it moves the relevant edge) and block (how to voice it).

    Inherits the same availability window (`unlock_at`/`lock_at`) as base tags,
    so scenario reactions come and go as the story develops — an early stupor tag
    can lock once the character finds its feet while new tags unlock in its place.
    """

    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=_NAME_PATTERN)
    description: str = Field(min_length=1)
    sentiment: str = Field(default="neutral", pattern=r"^(positive|negative|neutral)$")
    delta: DeltaVector = Field(default_factory=DeltaVector)
    block: str = ""


class ScenePack(BaseModel):
    """The fully validated ScenePack (shape-level)."""

    model_config = ConfigDict(extra="forbid")

    spec_version: int
    meta: SceneMeta
    # Shared backdrop / premise, pinned for the whole cast. May be empty (a bare
    # group chat with no particular setting).
    setting: str = ""
    # Character pack names to bring on stage.
    cast: list[str] = Field(min_length=MIN_CAST, max_length=MAX_CAST)
    # Starting feelings on directed edges (optional; omitted edges start neutral).
    relationships: list[RelationshipSeed] = Field(default_factory=list)
    # Extra tags the setting grants specific actors, keyed by cast member id.
    scenario_tags: dict[str, list[ScenarioTag]] = Field(default_factory=dict)
    # group_chat = the user has a seat; play = the user is the narrator/suffleur.
    mode: str = Field(default="group_chat", pattern=r"^(group_chat|play)$")
    # Who picks the next speaker by default: the model, or the narrator/user.
    director: str = Field(default="model", pattern=r"^(model|narrator)$")

    @model_validator(mode="after")
    def _cross_references(self) -> ScenePack:
        cast = self.cast
        cast_set = set(cast)

        if len(cast) != len(cast_set):
            raise ValueError("cast members must be unique")
        if USER_ID in cast_set:
            raise ValueError(f"{USER_ID!r} is reserved for the human and cannot be a cast member")

        participants = cast_set | {USER_ID}
        for edge in self.relationships:
            if edge.from_ not in participants:
                raise ValueError(f"relationship 'from' {edge.from_!r} is not in the cast")
            if edge.to not in participants:
                raise ValueError(f"relationship 'to' {edge.to!r} is not in the cast")

        for actor, tags in self.scenario_tags.items():
            if actor not in cast_set:
                raise ValueError(f"scenario_tags key {actor!r} is not a cast member")
            if len(tags) > MAX_SCENARIO_TAGS_PER_ACTOR:
                raise ValueError(
                    f"{actor!r} has {len(tags)} scenario tags; limit is "
                    f"{MAX_SCENARIO_TAGS_PER_ACTOR}"
                )
            ids = [t.id for t in tags]
            if len(ids) != len(set(ids)):
                raise ValueError(f"scenario tag ids for {actor!r} must be unique")

        return self
