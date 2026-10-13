"""Which axis stages and tag gates are read on.

A stage is a climate, and a climate must not change from one bad evening. Live 09.09 four
insults dropped closeness 0.935 → 0.797: on a ladder hanging on closeness that threatens to
turn the character itself BACK, not to spoil a mood. Being angry with a person and being
unable to let him go are different numbers, and the second can only be `bond`.

The field is optional and by default keeps the old behaviour: a pack written before it must
not notice it appeared.
"""
from __future__ import annotations

from engine.state import Axes, standing_ratio
from tests._packs import make_pack

LADDER = [
    {"id": "wary", "up_to": 0.05, "block": "At a distance."},
    {"id": "helping", "up_to": 0.15, "block": "Helps."},
    {"id": "attached", "up_to": 0.30, "block": "Depends."},
    {"id": "keeping", "up_to": 0.50, "block": "Holds on."},
    {"id": "sabotage", "up_to": 0.75, "block": "Quietly gets in the way."},
    {"id": "obsessed", "up_to": 1.00, "block": "Does not let go."},
]


def test_the_default_is_what_every_pack_before_this_field_assumed():
    pack = make_pack()
    assert pack.stage_axis == "closeness"


def test_closeness_answers_how_she_is_right_now():
    axes = Axes(affection=90.0, trust=70.0, bond=5.0)
    assert standing_ratio(axes, 100.0) == 0.8
    assert standing_ratio(axes, 100.0, "closeness") == 0.8


def test_bond_answers_what_they_are_to_her_at_all():
    axes = Axes(affection=90.0, trust=70.0, bond=5.0)
    assert standing_ratio(axes, 100.0, "bond") == 0.05


def test_a_bad_evening_does_not_unwind_a_bond_ladder():
    """The claim the field exists for.

    The same four insults: on closeness they drop her a stage down, on bond they do not move the
    ladder at all. Both axes are checked at once, because "did not turn back" means nothing
    without "but on the other axis it would have".
    """
    pack = make_pack(stages=LADDER)
    before = Axes(affection=93.5, trust=93.5, bond=60.0)   # closeness 0.935, bond 0.60
    after = Axes(affection=61.5, trust=65.5, bond=58.4)    # four insults −8/−7/−0.4

    from engine.state import resolve_stage
    close_before = resolve_stage(standing_ratio(before, 100.0, "closeness"), pack.stages)
    close_after = resolve_stage(standing_ratio(after, 100.0, "closeness"), pack.stages)
    bond_before = resolve_stage(standing_ratio(before, 100.0, "bond"), pack.stages)
    bond_after = resolve_stage(standing_ratio(after, 100.0, "bond"), pack.stages)

    assert close_before.id == "obsessed"
    assert close_after.id == "sabotage", "on closeness the character rolls back a stage"
    assert bond_before.id == bond_after.id == "sabotage", "on bond the ladder does not move"


def test_the_ladder_still_falls_when_the_bond_itself_is_spent():
    """One-way does not mean motionless.

    Killing by her own hand someone who was different costs bond. Otherwise the ladder would be
    not slow but irreversible, and the price would stop existing.
    """
    pack = make_pack(stages=LADDER)
    from engine.state import resolve_stage
    high = Axes(affection=50.0, trust=50.0, bond=51.0)
    spent = Axes(affection=50.0, trust=50.0, bond=49.0)
    assert resolve_stage(standing_ratio(high, 100.0, "bond"), pack.stages).id == "sabotage"
    assert resolve_stage(standing_ratio(spent, 100.0, "bond"), pack.stages).id == "keeping"


def test_tag_windows_read_the_same_axis_as_the_stages():
    """Otherwise "she became different" and "something different became available to her" happen at
    different moments.

    Checked through the runtime, not arithmetic: that is the only place they can diverge.
    """
    import json

    from engine.character import CharacterRuntime

    class _Says:
        def __init__(self, tag):
            self._tag = tag

        def chat(self, messages, *, model=None, fmt=None, options=None):
            return json.dumps({"tag": self._tag}) if fmt is not None else "..."

    pack = make_pack(
        stage_axis="bond",
        stages=LADDER,
        tags=[
            {"id": "warmth", "description": "Warmth.", "sentiment": "positive"},
            {"id": "hostility", "description": "Rudeness.", "sentiment": "negative"},
            {"id": "neutral", "description": "Ordinary.", "sentiment": "neutral"},
            # Available only on the upper half of the ladder.
            {"id": "possessive", "description": "Jealousy.", "sentiment": "negative",
             "unlock_at": 0.5},
        ],
        deltas={
            "warmth": {"affection": 5.0, "trust": 3.0, "bond": 0.5},
            "hostility": {"affection": -6.0, "trust": -4.0, "bond": -0.2},
            "neutral": {"affection": 0.0, "trust": 0.0, "bond": 0.0},
            "possessive": {"affection": -1.0, "trust": -1.0, "bond": 0.0},
        },
        blocks={"warmth": "a", "hostility": "b", "neutral": "", "possessive": "c"},
    )

    from engine.state import StateKernel

    # High closeness, low bond: the gates must be CLOSED, though the mood is excellent.
    warm_stranger = StateKernel(pack.axes, values={"affection": 95.0, "trust": 95.0, "bond": 5.0})
    got = CharacterRuntime(pack, _Says("possessive"), state=warm_stranger).respond("who was that")
    assert got.tag == pack.meta.fallback_tag

    # And the other way round: high bond, a spoiled mood — the gates are open.
    bonded = StateKernel(pack.axes, values={"affection": 20.0, "trust": 10.0, "bond": 80.0})
    got = CharacterRuntime(pack, _Says("possessive"), state=bonded).respond("who was that")
    assert got.tag == "possessive"
