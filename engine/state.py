"""State kernel — the numeric heart of a character's disposition.

Three axes (affection / trust / bond) moved only by the engine from a pack's
delta table, clamped to [0, axis_max], decayed toward baseline on idle. The LLM
never reads or writes these numbers.

The axis ceiling is a single runtime value (`axis_max`) rather than per-pack
bounds. Raising it makes the same deltas a smaller fraction of the whole, which
is the slow-burn knob: packs stay unchanged, relationships just warm slower.

This module is deliberately the narrowest possible numeric surface: pure
arithmetic, no I/O, no LLM. It is the seam a native (e.g. Rust) core could
replace later without touching contracts or prompt assembly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from engine.pack.models import AxesConfig, DecayConfig, DeltaVector, Stage

_AXES = ("affection", "trust", "bond")

DEFAULT_AXIS_MAX = 100.0


@dataclass(frozen=True)
class Axes:
    """An immutable snapshot of the three axis values."""

    affection: float
    trust: float
    bond: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _decay_toward(current: float, baseline: float, amount: float) -> float:
    """Move `current` toward `baseline` by at most `amount` (never overshoot)."""
    if amount <= 0 or current == baseline:
        return current
    if current > baseline:
        return max(baseline, current - amount)
    return min(baseline, current + amount)


class StateKernel:
    """Holds and evolves the three axes for one character session."""

    def __init__(
        self,
        axes_config: AxesConfig,
        *,
        axis_max: float = DEFAULT_AXIS_MAX,
        values: dict[str, float] | None = None,
    ) -> None:
        self._max = float(axis_max)
        # A start above the ceiling is clamped rather than rejected, so raising
        # the ceiling never invalidates an existing pack.
        self._start = {
            name: _clamp(float(getattr(axes_config, name).start), 0.0, self._max)
            for name in _AXES
        }
        if values is None:
            self._values = dict(self._start)
        else:
            self._values = {
                name: _clamp(float(values[name]), 0.0, self._max) for name in _AXES
            }

    @classmethod
    def from_pack(cls, pack, *, axis_max: float = DEFAULT_AXIS_MAX) -> StateKernel:
        return cls(pack.axes, axis_max=axis_max)

    @classmethod
    def restore(
        cls, pack, values: dict[str, float], *, axis_max: float = DEFAULT_AXIS_MAX
    ) -> StateKernel:
        """Rebuild a kernel from persisted axis values (session resume)."""
        return cls(pack.axes, axis_max=axis_max, values=values)

    @property
    def axis_max(self) -> float:
        return self._max

    @property
    def axes(self) -> Axes:
        return Axes(**self._values)

    def apply(self, delta: DeltaVector) -> Axes:
        """Add a delta vector to the axes, clamped to [0, axis_max]."""
        for name in _AXES:
            self._values[name] = _clamp(
                self._values[name] + getattr(delta, name), 0.0, self._max
            )
        return self.axes

    def decay(self, decay: DecayConfig) -> Axes:
        """Pull each axis toward its baseline (its configured start value)."""
        for name in _AXES:
            self._values[name] = _decay_toward(
                self._values[name], self._start[name], getattr(decay, name)
            )
        return self.axes

    def to_dict(self) -> dict[str, float]:
        return dict(self._values)


def relationship_ratio(axes: Axes, axis_max: float) -> float:
    """Combined closeness in [0, 1] from affection and trust.

    Mirrors the full engine's stage driver: liking and trust averaged. Bond is
    the slow long-term axis and does not gate the acted stage.
    """
    if axis_max <= 0:
        return 0.0
    aff = _clamp(axes.affection / axis_max, 0.0, 1.0)
    tru = _clamp(axes.trust / axis_max, 0.0, 1.0)
    return (aff + tru) / 2.0


def resolve_stage(ratio: float, stages: list[Stage]) -> Stage | None:
    """Return the active stage for a closeness ratio, or None when a pack
    declares no stages. Stages are ordered by ascending threshold; the first
    whose `up_to` covers the ratio wins, with the last as the catch-all."""
    if not stages:
        return None
    for stage in stages:
        if ratio <= stage.up_to:
            return stage
    return stages[-1]
