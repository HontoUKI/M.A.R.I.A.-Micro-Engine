"""State kernel — the numeric heart of a character's disposition.

Three axes (affection / trust / bond) moved only by the engine from a pack's
delta table, clamped to bounds, decayed toward baseline on idle. The LLM never
reads or writes these numbers.

This module is deliberately the narrowest possible numeric surface: pure
arithmetic, no I/O, no LLM. It is the seam a native (e.g. Rust) core could
replace later without touching contracts or prompt assembly.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from engine.pack.models import AxesConfig, DecayConfig, DeltaVector

_AXES = ("affection", "trust", "bond")


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

    def __init__(self, axes_config: AxesConfig, values: dict[str, float] | None = None) -> None:
        self._cfg = {name: getattr(axes_config, name) for name in _AXES}
        if values is None:
            self._values = {name: float(self._cfg[name].start) for name in _AXES}
        else:
            self._values = {name: float(values[name]) for name in _AXES}

    @classmethod
    def from_pack(cls, pack) -> StateKernel:
        return cls(pack.axes)

    @classmethod
    def restore(cls, pack, values: dict[str, float]) -> StateKernel:
        """Rebuild a kernel from persisted axis values (session resume)."""
        return cls(pack.axes, values)

    @property
    def axes(self) -> Axes:
        return Axes(**self._values)

    def apply(self, delta: DeltaVector) -> Axes:
        """Add a delta vector to the axes, clamped to each axis's bounds."""
        for name in _AXES:
            cfg = self._cfg[name]
            self._values[name] = _clamp(
                self._values[name] + getattr(delta, name), cfg.min, cfg.max
            )
        return self.axes

    def decay(self, decay: DecayConfig) -> Axes:
        """Pull each axis toward its baseline (its configured start value)."""
        for name in _AXES:
            self._values[name] = _decay_toward(
                self._values[name], self._cfg[name].start, getattr(decay, name)
            )
        return self.axes

    def to_dict(self) -> dict[str, float]:
        return dict(self._values)


def _axis_fraction(value: float, cfg) -> float:
    span = cfg.max - cfg.min
    if span <= 0:
        return 0.0
    return max(0.0, min(1.0, (value - cfg.min) / span))


def relationship_ratio(axes: Axes, config: AxesConfig) -> float:
    """Combined closeness in [0, 1] from affection and trust.

    Mirrors the full engine's stage driver: liking and trust averaged. Bond is
    the slow long-term axis and does not gate the acted stage.
    """
    aff = _axis_fraction(axes.affection, config.affection)
    tru = _axis_fraction(axes.trust, config.trust)
    return (aff + tru) / 2.0


# Ratio thresholds for the canonical stage ladder, mirroring the full engine's
# `classify_relationship_stage` (minus its mood/irritation override modes).
_STAGE_THRESHOLDS = (
    (0.12, "cold"),
    (0.25, "reserved"),
    (0.45, "cautious"),
    (0.65, "comfort"),
    (0.82, "close"),
)


def classify_stage(axes: Axes, config: AxesConfig) -> str:
    """Return the canonical relationship stage for the current axes."""
    ratio = relationship_ratio(axes, config)
    for threshold, name in _STAGE_THRESHOLDS:
        if ratio < threshold:
            return name
    return "very_close"


_BANDS = ("very low", "low", "moderate", "high", "very high")


def summarize_axes(axes: Axes, config: AxesConfig) -> str:
    """Render the axes as neutral qualitative bands for the prompt tail.

    Bands rather than raw numbers on purpose: a weak model is far less likely
    to parrot "affection: 34" back at the user than a soft descriptor, and the
    engine stays character-neutral (the pack's steering block carries tone).
    """
    parts: list[str] = []
    for name in _AXES:
        cfg = getattr(config, name)
        span = cfg.max - cfg.min
        frac = 0.0 if span <= 0 else (getattr(axes, name) - cfg.min) / span
        idx = min(len(_BANDS) - 1, max(0, int(frac * len(_BANDS))))
        parts.append(f"{name}: {_BANDS[idx]}")
    return ", ".join(parts)
