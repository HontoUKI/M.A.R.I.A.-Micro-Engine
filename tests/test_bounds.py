"""Пределы того, что она делает руками (§5 концепта: задержать, а не отнять).

Гейты тегов решают, что она может почувствовать; эти — что она может СДЕЛАТЬ. Разница не
косметическая: тег живёт один ход, а поступок меняет мир навсегда, и убитый житель не
отыгрывается обратно ни ступенью, ни настроением.

Проверяется здесь узость, а не сам запрет: правило, которое шире своего вреда, отнимает
у неё игру, ради которой всё и затевалось.
"""
from __future__ import annotations

import json

import pytest

from engine.character import CharacterRuntime
from engine.hands import GamePort
from engine.pack.models import ActionBound
from engine.state import StateKernel
from tests._packs import make_pack


class _Says:
    """Модель, которая всегда отвечает одной и той же строкой с `DO:`."""

    def __init__(self, line: str, tag: str = "neutral") -> None:
        self._line = line
        self._tag = tag

    def chat(self, messages, *, model=None, fmt=None, options=None):
        return json.dumps({"tag": self._tag}) if fmt is not None else self._line


class _Hands(GamePort):
    """Руки, которые ничего не делают, но помнят, что им сказали."""

    def __init__(self) -> None:
        self.taken = []

    def offer(self):
        return {"game": "test", "affordances": [{"verb": "take_from"}, {"verb": "fight"}]}

    def sight(self):
        return {}

    def history(self):
        return []

    def act(self, intention):
        self.taken.append(intention)


def _pack(**more):
    return make_pack(stage_axis="bond", **more)


def _runtime(pack, line, *, bond: float, hands):
    state = StateKernel(pack.axes, values={"affection": 50.0, "trust": 50.0, "bond": bond})
    return CharacterRuntime(pack, _Says(line), state=state, hands=hands)


def test_a_pack_without_bounds_forbids_nothing():
    hands = _Hands()
    got = _runtime(_pack(), "sure.\n<play>\nDO: fight {\"object\": \"villager\"}\n</play>",
                   bond=0.0, hands=hands).respond("go on")
    assert got.did, "движок сам за пак ничего не решает"
    assert hands.taken


def test_never_means_never_however_close_she_is():
    """Еда — не задержка. В мире, где смерть окончательна, это другое действие."""
    pack = _pack(bounds=[
        ActionBound(verb="take_from", object=["bread"], never=True, refuse="he lives on that"),
    ])
    hands = _Hands()
    got = _runtime(pack, 'ok.\n<play>\nDO: take_from {"object": "bread"}\n</play>',
                   bond=100.0, hands=hands).respond("take the bread")
    assert got.did == ()
    assert hands.taken == [], "до рук это не доехало"


def test_the_window_opens_on_the_stage_and_not_before():
    pack = _pack(bounds=[
        ActionBound(verb="fight", object=["villager"], unlock_at=0.75, refuse="not yet"),
    ])
    line = 'fine.\n<play>\nDO: fight {"object": "villager"}\n</play>'

    early = _Hands()
    _runtime(pack, line, bond=50.0, hands=early).respond("kill them")
    assert early.taken == [], "на 0.50 ворота закрыты"

    late = _Hands()
    _runtime(pack, line, bond=80.0, hands=late).respond("kill them")
    assert late.taken, "на 0.80 — её выбор"


def test_only_the_named_thing_is_held_back():
    """Один запрещённый шаг не отменяет всего решения."""
    pack = _pack(bounds=[ActionBound(verb="take_from", object=["bread"], never=True)])
    hands = _Hands()
    line = ('ok.\n<play>\nDO: take_from {"object": "bread"}\n'
            'DO: take_from {"object": "diamond"}\n</play>')
    got = _runtime(pack, line, bond=0.0, hands=hands).respond("clear the chest")
    assert len(hands.taken) == 1
    assert [g.verb for g in hands.taken[0].steps] == ["take_from"]
    assert hands.taken[0].steps[0].fields["object"] == "diamond"
    assert got.did


def test_taking_EVERYTHING_is_covered_by_the_bound():
    """Иначе граница обходится одним словом: `where.all` не называет ни одного предмета."""
    pack = _pack(bounds=[ActionBound(verb="take_from", object=["bread"], never=True)])
    hands = _Hands()
    got = _runtime(pack, 'ok.\n<play>\nDO: take_from {"where": {"all": true}}\n</play>',
                   bond=0.0, hands=hands).respond("take it all")
    assert hands.taken == []
    assert got.did == ()


def test_a_neighbouring_verb_is_not_touched():
    pack = _pack(bounds=[ActionBound(verb="take_from", object=["bread"], never=True)])
    hands = _Hands()
    _runtime(pack, 'ok.\n<play>\nDO: gather {"object": "bread"}\n</play>',
             bond=0.0, hands=hands).respond("get bread")
    assert hands.taken, "предел про сундук, а не про слово «хлеб»"


def test_never_cannot_be_a_window_in_disguise():
    with pytest.raises(ValueError):
        ActionBound(verb="take_from", never=True, unlock_at=0.99)


def test_she_is_TOLD_what_she_did_not_do():
    """Молча выброшенный шаг она прочитает как поломку и напишет ту же строку снова.

    Это уже было с нечитаемыми `DO:` 03.09, и лечится тем же способом: сказать ей. Без
    этой проверки предел был бы построен и до хода не доезжал — та самая повторяющаяся
    форма.
    """
    pack = _pack(bounds=[
        ActionBound(verb="take_from", object=["bread"], never=True, refuse="he lives on that"),
    ])
    hands = _Hands()
    runtime = _runtime(pack, 'ok.\n<play>\nDO: take_from {"object": "bread"}\n</play>',
                       bond=0.0, hands=hands)
    runtime.respond("take the bread")

    block = runtime._game_block()
    assert "did not do this" in block
    assert "he lives on that" in block, "причина, а не голый отказ"

    # И сказано ОДИН раз: жалоба, пережившая свой ход, становится шумом о прошлом.
    assert "did not do this" not in runtime._game_block()
