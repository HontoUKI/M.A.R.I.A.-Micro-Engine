"""The loop — a story that outlives the world (pack section `loop`).

A tag in `loop.arm_on` arms it. The next time the host reports a world whose id
differs from the one she last lived in, the counter steps — a new try — and stays.
From then on the step's block rides every turn.

Hidden by design: the counter is never part of a turn's result or any client
payload, and a relationship reset does not touch it. It lives in the session's
own `loop.json`, so only deleting the session's data clears it — that is what
«irreversible» means here.
"""
from __future__ import annotations

from dataclasses import dataclass

from engine.pack import CharacterPack


@dataclass
class LoopCounter:
    count: int = 0
    armed: bool = False
    world: str | None = None

    @classmethod
    def restore(cls, values: object) -> LoopCounter:
        if not isinstance(values, dict):
            return cls()
        world = values.get("world")
        return cls(
            count=max(0, int(values.get("count") or 0)),
            armed=bool(values.get("armed")),
            world=str(world) if world else None,
        )

    def to_dict(self) -> dict:
        return {"count": self.count, "armed": self.armed, "world": self.world}

    def entered(self, world: str | None) -> bool:
        """The host says which world this is. True when a new try began."""
        if not world:
            return False
        stepped = False
        if self.world is not None and world != self.world and self.armed:
            self.count += 1
            self.armed = False
            stepped = True
        self.world = world
        return stepped

    def after(self, tag: str, pack: CharacterPack) -> None:
        """A turn was read as `tag`; an arming tag arms the next world."""
        if pack.loop is not None and tag in pack.loop.arm_on:
            self.armed = True

    def block(self, pack: CharacterPack) -> str:
        """The step she is on, as prompt text; empty before the first step."""
        if pack.loop is None or self.count < 1:
            return ""
        steps = pack.loop.steps
        return steps[min(self.count, len(steps)) - 1].block
