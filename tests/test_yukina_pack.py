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

# Ступени, на которых открываются ворота — по СВЯЗИ, а не по настроению (09.09). Держатся
# здесь, чтобы правка числа в паке была видна как правка утверждения, а не как молча
# уехавшее поведение.
ATTACHED = 0.15   # он ушёл, он вернулся, ему грозит опасность
JEALOUS = 0.30    # кто-то ещё
KEEPING = 0.50    # взаимность и «отстань» как то, чего она не принимает

LOCKED_EARLY = {"he_left", "he_came_back", "he_is_in_danger", "someone_else",
                "told_to_back_off", "intimacy_return"}


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
    # Лестница висит на СВЯЗИ: плохой вечер портит настроение и не разворачивает арку.
    assert pack.stage_axis == "bond"
    assert [s.id for s in pack.stages] == [
        "wary", "helping", "attached", "keeping", "sabotage", "obsessed",
    ]
    # Ворота стоят на границах ступеней: иначе «она стала другой» и «ей стало доступно
    # другое» происходили бы в разные моменты.
    assert pack.tag("he_is_in_danger").unlock_at == ATTACHED
    assert pack.tag("someone_else").unlock_at == JEALOUS
    assert pack.tag("he_left").unlock_at == ATTACHED
    # Уход и возвращение — одни ворота: заметить только половину значило бы, что он
    # уходит навсегда.
    assert pack.tag("he_came_back").unlock_at == pack.tag("he_left").unlock_at
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
    assert "he_is_in_danger" in at(ATTACHED)          # открывается НА пороге
    assert "he_is_in_danger" not in at(ATTACHED - 0.01)
    assert {"intimacy_push", "intimacy_return"} <= at(KEEPING)
    assert "intimacy_push" not in at(KEEPING + 0.001)  # и закрывается сразу за ним


def test_a_stranger_is_not_offered_the_possessive_reads(pack):
    offered = {t.id for t in _available_tags(pack, ratio=0.02)}
    assert offered.isdisjoint(LOCKED_EARLY)
    # А обычные — на месте: пак не становится беднее, он становится другим.
    assert {"gift", "watched", "neglect", "intimacy_push"} <= offered


def test_once_she_is_attached_the_guarding_reads_appear(pack):
    offered = {t.id for t in _available_tags(pack, ratio=JEALOUS)}
    assert {"he_left", "he_came_back", "he_is_in_danger", "someone_else"} <= offered
    # Но не всё сразу: верхние ворота ещё закрыты.
    assert "intimacy_return" not in offered
    assert "told_to_back_off" not in offered


def test_at_the_top_the_romance_gate_flips(pack):
    offered = {t.id for t in _available_tags(pack, ratio=0.75)}
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
        pack, "who were you with", ratio=0.05
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


def test_coming_back_restores_and_does_not_pay(pack):
    """Уйти и вернуться — не дорога наверх.

    Иначе у неё появился бы способ добирать близость, которым игрок пользуется, ничего
    не делая: отойти на минуту и прийти. За полный круг доверие обязано остаться в
    минусе — оно и есть то, что уходом тратится.
    """
    left, back = pack.deltas["he_left"], pack.deltas["he_came_back"]
    assert back.affection > 0 and back.trust > 0
    assert left.trust + back.trust < 0
    assert back.affection < pack.deltas["gift"].affection


def test_being_killed_by_him_costs_the_stages_he_built(pack):
    """Убить её дорого, и цена записана числом, а не обещанием.

    Доверие — ровно то, что этим уничтожается: минус восемь при том, что самый крупный
    положительный ход даёт четыре. Ступени, набранные за вечер, осыпаются. Привязанность
    при этом держится почти вся — в этом и весь троп.
    """
    killed = pack.deltas["killed_by_him"]
    assert killed.trust <= -2 * pack.deltas["gift"].trust
    assert killed.affection > killed.trust
    assert abs(killed.bond) <= min(abs(killed.affection), abs(killed.trust))


def test_dying_to_the_world_moves_nothing(pack):
    """Крипер — не его поступок.

    То же правило, что у `on_your_own` и `he_is_in_danger`: отношения двигает то, что
    сделал ОН. Иначе неудачный прыжок читался бы как его вклад.
    """
    died = pack.deltas["died"]
    assert (died.affection, died.trust, died.bond) == (0.0, 0.0, 0.0)


def test_neither_death_is_gated(pack):
    """Умереть от его руки можно и в первый вечер.

    Ворота держат собственничество, а не способность заметить собственную смерть: тег,
    открытый только близким, оставил бы незнакомку без слов ровно там, где сказать
    нужнее всего.
    """
    early = {t.id for t in _available_tags(pack, ratio=0.01)}
    assert {"killed_by_him", "died"} <= early


def test_wanting_things_is_a_moment_and_not_the_character(pack):
    """Замечание автора 09.09: «с постоянными просьбами больше на пирата похожа».

    Счёт подаркам стоял в `identity`, то есть звучал КАЖДЫЙ ход независимо от повода, —
    и она выпрашивала вещи в каждой реплике. Место этой черты — в поводе, который про
    подарок, и в подсказке рядом с сообщением.
    """
    assert "keep score" not in pack.identity
    assert "diamond" not in pack.identity.lower()
    # А там, где повод действительно про подарок, она осталась целиком.
    assert "diamond" in pack.blocks["gift"].lower()
    assert pack.reply_directive, "ближняя подсказка сильнее дальнего правила"
    assert "attention" in pack.reply_directive.lower()


def test_the_dossier_is_weighed_on_every_turn_not_only_when_insulted(pack):
    """Названный факт и учтённый — разные вещи.

    Первый замер 09.09: досье стояло в промпте, и поведение не изменилось ни на реплику.
    Ход после грубости прочёлся как `attention`, чей блок велит просиять, — а указание
    свериться с записью сидело только в блоке `insult`, то есть срабатывало лишь когда
    грубят прямо сейчас. Заработало, когда встало туда, где звучит КАЖДЫЙ ход.
    """
    assert "note about what he has done" in pack.reply_directive
    # И блок про саму грубость тоже про неё знает: одного из двух мест мало.
    assert "note above" in pack.blocks["insult"]


def test_every_stage_has_a_cold_face(pack):
    """Ступень — климат, и климат обязан уметь быть плохим.

    Замечание автора: «она всё ещё добровата к игроку, который ведёт себя грубо». Одна из
    трёх причин была тут: все пять ступеней говорили только тёплое, вплоть до «ты прощаешь
    его раньше, чем он договорит извинение». Что бы он ни сделал минуту назад, климат
    велел быть преданной — и досье оставалось вежливой оговоркой.

    Холод у каждой ступени СВОЙ, потому что расстояние разное: незнакомка замолкает,
    близкая не уходит и перестаёт быть приятной.
    """
    for stage in pack.stages:
        assert "unkind lately" in stage.block, f"ступень {stage.id} не умеет холодеть"


def test_a_trinket_cannot_buy_off_an_insult(pack):
    """Живьём 09.09 он нагрубил четырежды и откупился ОДНОЙ стрелой.

    Подарком считалось всё отданное, поэтому мусор возвращал больше, чем стоило
    оскорбление, и грубость выходила бесплатной. Теперь у безделушки своя цена, и она
    меньше цены грубости в разы.
    """
    trinket, gift, insult = pack.deltas["trinket"], pack.deltas["gift"], pack.deltas["insult"]
    assert trinket.affection < gift.affection / 4
    assert trinket.affection < abs(insult.affection)
    assert trinket.trust < abs(insult.trust)


def test_rudeness_costs_more_than_the_biggest_kindness_returns(pack):
    """Иначе счёт всегда в его пользу, как бы он себя ни вёл."""
    insult, gift = pack.deltas["insult"], pack.deltas["gift"]
    assert abs(insult.trust) > gift.trust
