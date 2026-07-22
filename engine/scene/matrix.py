"""The relationship matrix — directed, per-pair feelings among a scene's cast.

One `StateKernel` per directed edge `source -> target`. Edges are sourced only
from **actors** (the cast), pointing at every other participant including the
user; the human's own feelings are not simulated, so there are no user-sourced
edges. Every edge is independent, which is what makes feelings **asymmetric**:
moving `A -> B` never touches `B -> A`. Megumin can adore Kaguya while Kaguya is
merely exasperated — two separate edges, each moved only on its owner's turns.

This reuses the v1 `StateKernel` unchanged: the matrix is just one kernel per
pair instead of one per character.
"""
from __future__ import annotations

from collections.abc import Iterable

from engine.pack.models import AxesConfig, AxisConfig, DeltaVector
from engine.scene.models import USER_ID, ScenePack
from engine.state import DEFAULT_AXIS_MAX, Axes, StateKernel

Edge = tuple[str, str]


def _axes_config(affection: float, trust: float, bond: float) -> AxesConfig:
    return AxesConfig(
        affection=AxisConfig(start=affection),
        trust=AxisConfig(start=trust),
        bond=AxisConfig(start=bond),
    )


class RelationshipMatrix:
    """Directed affection/trust/bond among a scene's participants."""

    def __init__(
        self,
        actors: Iterable[str],
        *,
        axis_max: float = DEFAULT_AXIS_MAX,
        seeds: dict[Edge, tuple[float, float, float]] | None = None,
        values: dict[Edge, dict[str, float]] | None = None,
    ) -> None:
        self._axis_max = float(axis_max)
        self._actors = list(actors)
        participants = set(self._actors) | {USER_ID}
        seeds = seeds or {}
        values = values or {}
        self._edges: dict[Edge, StateKernel] = {}
        for source in self._actors:
            for target in participants:
                if source == target:
                    continue
                # The seed is the edge's baseline (what it decays back toward);
                # persisted `values` set the current standing on top of it.
                config = _axes_config(*seeds.get((source, target), (0.0, 0.0, 0.0)))
                self._edges[(source, target)] = StateKernel(
                    config, axis_max=self._axis_max, values=values.get((source, target))
                )

    @classmethod
    def from_scene(
        cls,
        scene: ScenePack,
        *,
        axis_max: float = DEFAULT_AXIS_MAX,
        values: dict[Edge, dict[str, float]] | None = None,
    ) -> RelationshipMatrix:
        seeds: dict[Edge, tuple[float, float, float]] = {}
        for edge in scene.relationships:
            # User-sourced seeds are ignored: the human's feelings aren't the
            # engine's to hold. (The schema allows them for symmetry/future use.)
            if edge.from_ == USER_ID:
                continue
            seeds[(edge.from_, edge.to)] = (edge.affection, edge.trust, edge.bond)
        return cls(scene.cast, axis_max=axis_max, seeds=seeds, values=values)

    @property
    def actors(self) -> list[str]:
        return list(self._actors)

    def edges(self) -> list[Edge]:
        return list(self._edges)

    def _kernel(self, source: str, target: str) -> StateKernel:
        try:
            return self._edges[(source, target)]
        except KeyError:
            raise KeyError(
                f"no edge {source!r} -> {target!r}: source must be an actor and "
                f"target a different participant"
            ) from None

    def feeling(self, source: str, target: str) -> Axes:
        """How `source` currently feels about `target`."""
        return self._kernel(source, target).axes

    def apply(self, source: str, target: str, delta: DeltaVector) -> Axes:
        """Move only the `source -> target` edge. Never touches the reverse."""
        return self._kernel(source, target).apply(delta)

    def to_dict(self) -> dict[str, dict[str, float]]:
        """Persistable snapshot, keyed `"source->target"`."""
        return {f"{s}->{t}": k.to_dict() for (s, t), k in self._edges.items()}
