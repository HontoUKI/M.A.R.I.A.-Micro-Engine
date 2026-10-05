"""Mizuki: ballast that must not be lost.

The pack rests on three claims of the canon (`direction/MIZUKI_CONCEPT.md`), and all three
are numbers and code, not prose:

1. She starts BELOW neutral: trust in a person who pointed a gun at her is zero.
2. The biggest thing he can do is protect her, not give her gifts.
3. She has no fighting routines until the partner stage; her stance in danger is flight (router).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.pack import load_pack
from engine.perception import TagClassifier, _available_tags

_MIZUKI = Path(__file__).resolve().parents[1] / "characters" / "mizuki"

FOLLOWING = 0.15   # a pickaxe and blocks in her hands
USEFUL = 0.30      # the fear that he leaves alone; building
PARTNER = 0.50     # "you matter to me"


@pytest.fixture
def pack():
    return load_pack(str(_MIZUKI))


class _Insists:
    """A model that names the same tag whatever it is offered."""

    def __init__(self, tag: str) -> None:
        self._tag = tag

    def chat(self, messages, *, model=None, fmt=None, options=None):
        return json.dumps({"tag": self._tag})


def test_she_starts_below_neutral_because_he_pointed_a_gun(pack):
    assert pack.axes.trust.start == 0
    assert pack.axes.affection.start < 10


def test_protecting_her_is_the_biggest_thing_he_can_do(pack):
    """She does not need a diamond — she needs to live until tomorrow."""
    protected = pack.deltas["protected"]
    for tag, delta in pack.deltas.items():
        if tag != "protected":
            assert protected.trust >= delta.trust, tag
    assert protected.affection > pack.deltas["gift"].affection
    assert pack.deltas["fed"].affection > pack.deltas["gift"].affection


def test_pointing_the_gun_again_costs_more_than_protecting_her_returns(pack):
    threatened, protected = pack.deltas["threatened"], pack.deltas["protected"]
    assert abs(threatened.trust) > protected.trust
    assert pack.remembered_for["threatened"] > pack.remembered_for["protected"]


def test_the_world_happening_to_her_moves_nothing(pack):
    """A shot, a hunt for her, hunger — a state of affairs, not his deed."""
    for tag in ("gunfire", "you_are_hunted", "you_were_hurt", "hungry", "he_is_in_danger"):
        d = pack.deltas[tag]
        assert (d.affection, d.trust, d.bond) == (0.0, 0.0, 0.0), tag


def test_fear_of_losing_him_opens_only_once_she_knows_him(pack):
    early = {t.id for t in _available_tags(pack, ratio=0.05)}
    assert "dont_leave_me" not in early and "closeness" not in early
    assert "dont_leave_me" in {t.id for t in _available_tags(pack, ratio=USEFUL)}
    assert "closeness" in {t.id for t in _available_tags(pack, ratio=PARTNER)}


def test_a_locked_tag_cannot_be_chosen_even_when_the_model_names_it(pack):
    assert TagClassifier(_Insists("closeness")).classify(
        pack, "you matter to me", ratio=0.05
    ) == pack.meta.fallback_tag
    assert TagClassifier(_Insists("closeness")).classify(
        pack, "you matter to me", ratio=0.8
    ) == "closeness"


def test_no_fighting_until_she_is_his_partner(pack):
    """The author, 25.09: "no fighting routines at all at the start"."""
    for verb in ("fight", "strike", "beat"):
        bound = next(b for b in pack.bounds if b.verb == verb)
        assert bound.covers(verb, ("zombie",))
        assert not bound.allows(USEFUL), verb
        assert bound.allows(PARTNER), verb


def test_her_hands_open_with_the_stages(pack):
    build = next(b for b in pack.bounds if b.verb == "build")
    assert not build.allows(FOLLOWING) and build.allows(USEFUL)


def test_digging_is_the_worlds_rule_not_a_stage(pack):
    """A log by hand is unreal at any stage — the router holds this (`dig_with: iron`)."""
    assert not any(b.verb == "dig" for b in pack.bounds)


def test_she_will_not_kill_even_a_chicken_at_first(pack):
    fight = next(b for b in pack.bounds if b.verb == "fight")
    assert fight.covers("fight", ("chicken",)) and not fight.allows(USEFUL)


def test_she_never_takes_his_food(pack):
    food = next(b for b in pack.bounds if b.verb == "take_from")
    assert food.covers("take_from", ("bread",)) and not food.allows(1.0)
    assert not food.covers("take_from", ("iron_ingot",))


def test_every_stage_has_a_cold_face(pack):
    for stage in pack.stages:
        assert "unkind lately" in stage.block, f"stage {stage.id} cannot go cold"


def test_gunfire_is_read_by_the_stage(pack):
    """One occasion, different stages: she flinches at the start, is calm as a partner."""
    assert "stage note" in pack.blocks["gunfire"]
    by_id = {s.id: s.block for s in pack.stages}
    assert "flinch" in by_id["shock"]
    assert "not afraid of the gunfire" in by_id["partner"]


def test_no_japanese_words_are_invited(pack):
    """The author, 25.09: "Kowai from the very start — not great". The pack must not call up Japanese words."""
    text = " ".join([pack.identity, *pack.blocks.values(), *(s.block for s in pack.stages)]).lower()
    for word in ("kowai", "itadakimasu", "sugoi", "japanese word"):
        assert word not in text, word


def _flat(text):
    return " ".join(str(text).split())


def test_nothing_unseen_is_invited(pack):
    """Live 26.09: "noise like a factory" at a tree in the forest, "a vending machine" at a bed.

    The `progress` block suggested comparing ANY advancement with a factory, a train, a vending
    machine, her own included; her identity called for comparing everything with home. The pack
    must not suggest a single thing she has not seen.
    """
    text = " ".join([pack.identity, *pack.blocks.values(), *(s.block for s in pack.stages)]).lower()
    for word in ("factory", "vending machine"):
        assert word not in text, word
    assert "compare what you actually see here to home" in _flat(pack.identity)
    # "Invent nothing" is not her trait but a game mode: GAMER=true (engine/character.py).
    assert not any("never describe a machine" in i.lower() for i in pack.invariants)


def test_she_does_not_see_advancements(pack):
    """The author, 27.09: "close her eyes to advancements — this is story RP".

    An advancement is the game's score, not something that happens to her; live 26.09 a bed
    ("Sweet Dreams") became a "vending machine" for her. The `advanced` note does not reach her,
    and the pack has no tags fed only by it.
    """
    from tools.play import visible

    assert "advanced" in pack.unseen_notes
    unseen = frozenset(pack.unseen_notes)
    assert not visible({"kind": "advanced", "who": "Mizuki", "what": "Sweet Dreams"}, unseen)
    assert visible({"kind": "given", "who": "HontoUKI"}, unseen), "what he does still reaches her"
    assert not {"progress", "she_did"} & {t.id for t in pack.tags}


def test_home_is_not_one_memory_on_repeat(pack):
    """Live 26.09: "the eight o'clock train" five times in a morning — the block's example became the answer."""
    block = _flat(pack.blocks["asks_about_home"])
    assert "you have not told him yet" in block
    assert "train at eight" not in block


def test_small_talk_has_its_own_tags_and_neglect_is_narrow():
    """30.09: without small-talk tags the classifier filed chatter under story tags —
    short on-topic answers as `neglect` ("you don't listen to me anyway" ×3), mock
    politeness as `attention` answered literally — and «teasing» told her to say «at
    home I would explain», five times in one evening."""
    pack = load_pack(str(_MIZUKI))
    ids = {t.id for t in pack.tags}
    assert {"small_talk", "joke", "sarcasm"} <= ids
    assert "mundane" not in ids
    assert pack.tag("small_talk").sentiment == "neutral", "chatter is not a deed in the dossier"
    assert pack.deltas["small_talk"].trust > 0, "small talk raises trust, slowly"
    assert "joke" in pack.diminishing
    assert "NOT neglect" in pack.tag("neglect").description
    assert "literally" in pack.blocks["sarcasm"]
    assert "home" not in pack.blocks["teasing"].split("Do not bring up home")[0]


def test_his_death_is_read_by_the_stage(pack):
    # Neutral → light sadness → bitterness: one fact, three windows, and exactly one in each.
    died = ("he_died", "he_died_missed", "he_died_grief")
    for bond, want in ((0.05, "he_died"), (0.30, "he_died_missed"), (0.80, "he_died_grief")):
        offered = [t.id for t in _available_tags(pack, ratio=bond) if t.id in died]
        assert offered == [want], (bond, offered)
    assert all(
        (pack.deltas[t].affection, pack.deltas[t].trust, pack.deltas[t].bond) == (0, 0, 0)
        for t in died
    ), "his death is not his deed toward her"


def test_the_loop_arms_only_on_grief_and_the_warning_is_on_the_box(pack):
    # The loop is armed only by grief (bond from 0.5), and the warning stands in the pack's description.
    assert pack.loop.arm_on == ["he_died_grief"]
    assert len(pack.loop.steps) == 3
    assert "irreversible consequences" in pack.meta.description
    assert "0.5" in pack.meta.description
