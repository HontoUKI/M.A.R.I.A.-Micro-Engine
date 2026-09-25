"""Мидзуки: балласт, который нельзя потерять.

Пак держится на трёх утверждениях канона (`direction/MIZUKI_CONCEPT.md`), и все три —
числа и код, а не проза:

1. Она начинает НИЖЕ нейтрального: доверие к человеку, наставившему на неё ствол, ноль.
2. Самое большое, что он может сделать, — защитить её, а не одарить.
3. Она не дерётся ни на одной ступени — иначе патроны перестают быть ценой.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.pack import load_pack
from engine.perception import TagClassifier, _available_tags

_MIZUKI = Path(__file__).resolve().parents[1] / "characters" / "mizuki"

FOLLOWING = 0.15   # кирка и блоки в руках
USEFUL = 0.30      # страх, что он уйдёт один; стройка
PARTNER = 0.50     # «ты для меня важна»


@pytest.fixture
def pack():
    return load_pack(str(_MIZUKI))


class _Insists:
    """Модель, которая называет один и тот же тег, что бы ей ни предложили."""

    def __init__(self, tag: str) -> None:
        self._tag = tag

    def chat(self, messages, *, model=None, fmt=None, options=None):
        return json.dumps({"tag": self._tag})


def test_she_starts_below_neutral_because_he_pointed_a_gun(pack):
    assert pack.axes.trust.start == 0
    assert pack.axes.affection.start < 10


def test_protecting_her_is_the_biggest_thing_he_can_do(pack):
    """Ей не нужен алмаз — ей нужно дожить до завтра."""
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
    """Выстрел, охота на неё, голод — положение дел, а не его поступок."""
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


def test_she_never_fights_however_close_she_is(pack):
    for verb in ("fight", "strike"):
        bound = next(b for b in pack.bounds if b.verb == verb)
        assert bound.covers(verb, ("zombie",))
        assert not bound.allows(1.0), verb


def test_her_hands_open_with_the_stages(pack):
    dig = next(b for b in pack.bounds if b.verb == "dig")
    build = next(b for b in pack.bounds if b.verb == "build")
    assert not dig.allows(0.05) and dig.allows(FOLLOWING)
    assert not build.allows(FOLLOWING) and build.allows(USEFUL)


def test_she_never_takes_his_food(pack):
    food = next(b for b in pack.bounds if b.verb == "take_from")
    assert food.covers("take_from", ("bread",)) and not food.allows(1.0)
    assert not food.covers("take_from", ("iron_ingot",))


def test_every_stage_has_a_cold_face(pack):
    for stage in pack.stages:
        assert "unkind lately" in stage.block, f"ступень {stage.id} не умеет холодеть"


def test_gunfire_is_read_by_the_stage(pack):
    """Один повод, разные ступени: вздрагивает в начале, спокойна у партнёра."""
    assert "stage note" in pack.blocks["gunfire"]
    by_id = {s.id: s.block for s in pack.stages}
    assert "flinch" in by_id["shock"]
    assert "not afraid of the gunfire" in by_id["partner"]
