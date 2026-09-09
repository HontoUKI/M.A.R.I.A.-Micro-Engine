"""Юкина: привязанность открывает то, чего до неё нет.

Пак держится на одном утверждении, и оно не про прозу: собственничество, ревность
и опека живут в ОКНЕ по близости, а вне окна движок не показывает тег
классификатору вовсе. То есть это не «мы попросили модель не ревновать рано» —
выбрать нечего.

Проверяется именно это, обеими сторонами (R27): и что запертого тега нет в
предложенном списке, и что модель, которая всё равно его назовёт, получит
fallback. Первое — про витрину, второе — про гарантию, и совпадать они не обязаны.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.pack import load_pack
from engine.perception import TagClassifier, _available_tags

_YUKINA = Path(__file__).resolve().parents[1] / "characters" / "yukina"

# Ступени, на которых открываются ворота. Держатся здесь, чтобы правка числа в паке
# была видна как правка утверждения, а не как молча уехавшее поведение.
GUARDING = 0.45   # опека, ревность, «он ушёл»
KEEPING = 0.7     # взаимность и «отстань» как то, что она не принимает

LOCKED_EARLY = {"he_left", "he_is_in_danger", "someone_else", "told_to_back_off",
                "intimacy_return"}


@pytest.fixture
def pack():
    return load_pack(str(_YUKINA))


class _Insists:
    """Модель, которая называет один и тот же тег, что бы ей ни предложили."""

    def __init__(self, tag: str) -> None:
        self._tag = tag

    def chat(self, messages, *, model=None, fmt=None, options=None):
        return json.dumps({"tag": self._tag})


def test_pack_is_the_yandere_rework(pack):
    assert pack.meta.name == "yukina"
    assert [s.id for s in pack.stages] == [
        "newcomer", "friends", "possessive", "devoted", "inseparable",
    ]
    # Ворота стоят там же, где границы ступеней: иначе «она стала другой» и «ей
    # стало доступно другое» происходили бы в разные моменты.
    assert pack.tag("he_is_in_danger").unlock_at == GUARDING
    assert pack.tag("someone_else").unlock_at == GUARDING
    assert pack.tag("he_left").unlock_at == GUARDING
    assert pack.tag("intimacy_return").unlock_at == KEEPING
    assert pack.tag("told_to_back_off").unlock_at == KEEPING
    # Отказ и взаимность — одни ворота с двух сторон, и зазора между ними нет.
    assert pack.tag("intimacy_push").lock_at == pack.tag("intimacy_return").unlock_at


def test_the_gate_edges_are_inclusive_on_both_sides(pack):
    """Что происходит РОВНО на пороге, а не рядом с ним.

    Окно проверяется как `unlock_at <= ratio <= lock_at`, то есть обе границы
    входят, и на самой отметке 0.7 доступны и отказ, и взаимность разом. Это не
    дефект и не задумка — это следствие, и записано оно здесь, чтобы правка
    сравнения в движке падала тестом, а не всплывала в игре одним странным ходом.
    """
    at = lambda r: {t.id for t in _available_tags(pack, r)}  # noqa: E731
    assert "he_is_in_danger" in at(GUARDING)          # открывается НА пороге
    assert "he_is_in_danger" not in at(GUARDING - 0.01)
    assert {"intimacy_push", "intimacy_return"} <= at(KEEPING)
    assert "intimacy_push" not in at(KEEPING + 0.001)  # и закрывается сразу за ним


def test_a_stranger_is_not_offered_the_possessive_reads(pack):
    offered = {t.id for t in _available_tags(pack, ratio=0.1)}
    assert offered.isdisjoint(LOCKED_EARLY)
    # А обычные — на месте: пак не становится беднее, он становится другим.
    assert {"gift", "watched", "neglect", "intimacy_push"} <= offered


def test_once_she_is_attached_the_guarding_reads_appear(pack):
    offered = {t.id for t in _available_tags(pack, ratio=GUARDING)}
    assert {"he_left", "he_is_in_danger", "someone_else"} <= offered
    # Но не всё сразу: верхние ворота ещё закрыты.
    assert "intimacy_return" not in offered
    assert "told_to_back_off" not in offered


def test_at_the_top_the_romance_gate_flips(pack):
    offered = {t.id for t in _available_tags(pack, ratio=0.85)}
    assert "intimacy_return" in offered
    assert "told_to_back_off" in offered
    # Отказ ухаживанию перестаёт существовать ровно там, где появляется ответ на него.
    assert "intimacy_push" not in offered


def test_a_locked_tag_cannot_be_chosen_even_when_the_model_names_it(pack):
    """Гарантия, а не витрина.

    Список — это то, что модель видит; проверять надо то, что она может ПОЛУЧИТЬ.
    Модель, назвавшая запертый тег, обязана уехать в fallback, иначе весь гейт
    держится на её послушании.
    """
    chosen = TagClassifier(_Insists("someone_else")).classify(
        pack, "who were you with", ratio=0.1
    )
    assert chosen == pack.meta.fallback_tag
    # И тот же самый ответ модели выше ворот проходит — иначе тест доказывал бы
    # сломанный классификатор, а не работающий гейт.
    assert TagClassifier(_Insists("someone_else")).classify(
        pack, "who were you with", ratio=0.8
    ) == "someone_else"


def test_a_gift_is_the_single_biggest_thing_he_can_do(pack):
    """«Девушки любят бриллианты» — как число, а не как реплика."""
    gift = pack.deltas["gift"]
    others = [d.affection for tag, d in pack.deltas.items() if tag != "gift"]
    assert gift.affection > max(others)
    assert abs(gift.bond) <= min(abs(gift.affection), abs(gift.trust))


def test_leaving_her_makes_her_cling_and_trust_less(pack):
    """Уход не остужает — он сгущает.

    Единственная строка в таблице, где оси расходятся в РАЗНЫЕ стороны: тянется
    сильнее, полагается меньше. Близость при этом обязана падать, иначе исчезновение
    было бы дорогой наверх.
    """
    left = pack.deltas["he_left"]
    assert left.affection > 0
    assert left.trust < 0
    assert left.affection + left.trust < 0


def test_danger_around_him_moves_nothing(pack):
    """Опасность — положение дел, а не его поступок.

    То же правило, которым 08.09 чинили `on_your_own`: отношения двигает то, что
    сделал ОН. Иначе ночь снаружи читалась бы как его вклад в их близость.
    """
    danger = pack.deltas["he_is_in_danger"]
    assert (danger.affection, danger.trust, danger.bond) == (0.0, 0.0, 0.0)
