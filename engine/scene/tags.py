"""An actor's full tag vocabulary within a scene.

Merges a character's base moment tags with the scene's scenario tags into one
list, resolving each tag's delta and block so the runtime has a single lookup.
The base-vs-scenario collision check that the ScenePack loader had to defer (it
has no character packs) happens here, at scene assembly.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.pack.models import CharacterPack, DeltaVector
from engine.scene.errors import SceneValidationError
from engine.scene.models import ScenarioTag


@dataclass(frozen=True)
class SceneTag:
    """One tag available to an actor in a scene, delta and block resolved."""

    id: str
    description: str
    delta: DeltaVector
    block: str
    unlock_at: float = 0.0
    lock_at: float = 1.0

    def available_at(self, ratio: float) -> bool:
        return self.unlock_at <= ratio <= self.lock_at


class ActorTagset:
    """The base + scenario tags one actor can be classified into this scene."""

    def __init__(self, tags: list[SceneTag], fallback: str) -> None:
        self._tags: dict[str, SceneTag] = {t.id: t for t in tags}
        self._fallback = fallback

    @classmethod
    def build(
        cls, pack: CharacterPack, scenario_tags: list[ScenarioTag] | None
    ) -> ActorTagset:
        base_ids = {t.id for t in pack.tags}
        merged: list[SceneTag] = [
            SceneTag(
                t.id, t.description, pack.deltas[t.id], pack.blocks[t.id],
                t.unlock_at, t.lock_at,
            )
            for t in pack.tags
        ]
        for st in scenario_tags or []:
            if st.id in base_ids:
                raise SceneValidationError(
                    f"scenario tag {st.id!r} collides with a base tag of "
                    f"{pack.meta.name!r}"
                )
            merged.append(
                SceneTag(st.id, st.description, st.delta, st.block, st.unlock_at, st.lock_at)
            )
        return cls(merged, pack.meta.fallback_tag)

    @property
    def fallback(self) -> str:
        return self._fallback

    def get(self, tag_id: str) -> SceneTag:
        return self._tags[tag_id]

    def available(self, ratio: float) -> list[SceneTag]:
        """Tags offered to the classifier at this closeness ratio (the fallback
        is always kept, so there is always a valid choice)."""
        avail = [
            t for t in self._tags.values()
            if t.available_at(ratio) or t.id == self._fallback
        ]
        return avail or list(self._tags.values())
