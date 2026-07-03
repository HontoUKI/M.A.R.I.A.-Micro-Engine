"""State kernel contracts: delta application, clamping, decay, banding."""
from __future__ import annotations

import pytest

from engine.pack.models import DecayConfig, DeltaVector
from engine.state import Axes, StateKernel, classify_stage, relationship_ratio, summarize_axes
from tests._packs import make_pack


def _kernel():
    return StateKernel.from_pack(make_pack())


def test_starts_at_configured_baseline():
    axes = _kernel().axes
    assert axes.affection == 20
    assert axes.trust == 10
    assert axes.bond == 0


def test_apply_moves_axes_by_delta():
    k = _kernel()
    axes = k.apply(DeltaVector(affection=5.0, trust=3.0, bond=0.5))
    assert axes.affection == 25
    assert axes.trust == 13
    assert axes.bond == 0.5


def test_apply_clamps_to_upper_bound():
    k = _kernel()
    k.apply(DeltaVector(affection=1000.0, trust=1000.0, bond=1000.0))
    axes = k.axes
    assert axes.affection == 100
    assert axes.trust == 100
    assert axes.bond == 100


def test_apply_clamps_to_lower_bound():
    k = _kernel()
    axes = k.apply(DeltaVector(affection=-1000.0, trust=-1000.0, bond=-1000.0))
    assert axes.affection == 0
    assert axes.trust == 0
    assert axes.bond == 0


def test_decay_pulls_toward_baseline_without_overshoot():
    k = _kernel()
    k.apply(DeltaVector(affection=10.0, trust=10.0, bond=10.0))  # 30 / 20 / 10
    k.decay(DecayConfig(affection=2.0, trust=1.0, bond=0.1))
    axes = k.axes
    assert axes.affection == 28  # 30 → 28
    assert axes.trust == 19
    assert abs(axes.bond - 9.9) < 1e-9


def test_decay_never_crosses_baseline():
    k = _kernel()
    # affection start is 20; nudge just above and decay hard.
    k.apply(DeltaVector(affection=1.0, trust=1.0, bond=0.0))  # 21
    k.decay(DecayConfig(affection=50.0, trust=50.0, bond=0.0))
    assert k.axes.affection == 20  # snaps to baseline, not below


def test_restore_and_to_dict_roundtrip():
    pack = make_pack()
    k = StateKernel.from_pack(pack)
    k.apply(DeltaVector(affection=7.0, trust=2.0, bond=1.0))
    snapshot = k.to_dict()
    restored = StateKernel.restore(pack, snapshot)
    assert restored.to_dict() == snapshot


def test_summarize_axes_uses_neutral_bands_not_numbers():
    pack = make_pack()
    k = StateKernel.from_pack(pack)
    summary = summarize_axes(k.axes, pack.axes)
    assert "affection" in summary
    # A baseline of 20/100 is in the "low" band; no raw number leaks.
    assert "20" not in summary
    assert any(band in summary for band in ("very low", "low", "moderate", "high"))


# ---------------------------------------------------------------- stages


def _axes(affection, trust, bond=0.0):
    return Axes(affection=affection, trust=trust, bond=bond)


def test_relationship_ratio_averages_affection_and_trust():
    cfg = make_pack().axes  # 0..100 bounds
    assert relationship_ratio(_axes(40, 60), cfg) == pytest.approx(0.5)
    assert relationship_ratio(_axes(0, 0), cfg) == 0.0
    assert relationship_ratio(_axes(100, 100), cfg) == 1.0


@pytest.mark.parametrize(
    "affection,trust,expected",
    [
        (0, 0, "cold"),
        (11, 11, "cold"),
        (12, 12, "reserved"),
        (24, 24, "reserved"),
        (30, 30, "cautious"),
        (50, 50, "comfort"),
        (70, 70, "close"),
        (90, 90, "very_close"),
        (100, 100, "very_close"),
    ],
)
def test_classify_stage_ladder(affection, trust, expected):
    cfg = make_pack().axes
    assert classify_stage(_axes(affection, trust), cfg) == expected


def test_bond_does_not_affect_the_stage():
    cfg = make_pack().axes
    low_bond = classify_stage(_axes(50, 50, bond=0), cfg)
    high_bond = classify_stage(_axes(50, 50, bond=100), cfg)
    assert low_bond == high_bond == "comfort"
