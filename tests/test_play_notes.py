"""Записка мира про человека рядом: что именно она читает.

Роутер сообщает ФАКТ — «дал», «смотрит», «ушёл», «к нему что-то подобралось», — и
записка обязана донести его словами, не сделав за неё вывода. Проверяется здесь и то,
и другое: что содержание доезжает целиком и что оценки в нём нет.

Формы событий — не мои: их объявляет адаптер, таблица в его `minecraft/README.md`.
Ошибиться тут дёшево на вид и дорого на деле — поле, взятое СОСЕДНЕЕ с нужным, даёт
записку, которая выглядит правильной и всегда пуста.
"""
from __future__ import annotations

import re

import pytest

from tools.play import ABOUT_HIM, QUIET_AFTER_HIM, _note


def test_a_gift_says_who_and_what():
    said = _note({
        "kind": "given", "who": "HontoUKI",
        "took": [{"what": "diamond", "count": 2}, {"what": "iron_helmet", "count": 1}],
    })
    assert said == "[HontoUKI gave you diamond x2, iron_helmet]"
    # Единица не пишется: «iron_helmet x1» — это счёт, а не речь.
    assert "x1" not in said


def test_watching_says_whether_she_was_working():
    working = _note({
        "kind": "watched", "who": "HontoUKI", "watching_for": 7, "while_working": True,
    })
    idle = _note({
        "kind": "watched", "who": "HontoUKI", "watching_for": 7, "while_working": False,
    })
    assert "watching you work" in working
    assert "watching you" in idle and "you work" not in idle


def test_leaving_has_two_shapes_and_both_survive():
    # Ушёл ногами — это расстояние и время.
    walked = _note({"kind": "left", "who": "HontoUKI", "blocks": 63, "gone_for": 31})
    assert "63" in walked and "31" in walked
    # Вышел из игры — это другое, и «63 блока» здесь было бы выдумкой.
    out = _note({"kind": "left", "who": "HontoUKI", "why": "logged out"})
    assert out == "[HontoUKI logged out]"
    assert "blocks" not in out


def test_danger_names_what_and_how_close():
    said = _note({"kind": "at_risk", "who": "HontoUKI", "from": "creeper", "blocks": 2})
    assert said == "[a creeper is 2 blocks from HontoUKI]"


@pytest.mark.parametrize("event", [
    {"kind": "given", "who": "HontoUKI", "took": [{"what": "diamond", "count": 1}]},
    {"kind": "watched", "who": "HontoUKI", "watching_for": 9, "while_working": True},
    {"kind": "left", "who": "HontoUKI", "blocks": 63, "gone_for": 31},
    {"kind": "returned", "who": "HontoUKI", "blocks": 9},
    {"kind": "at_risk", "who": "HontoUKI", "from": "creeper", "blocks": 2},
])
def test_a_note_states_a_fact_and_never_a_reading(event):
    said = _note(event)
    # В скобках, как всё, что приходит не от человека: иначе записка неотличима от речи.
    assert said.startswith("[") and said.endswith("]")
    # Имя человека называется всегда — глагол про человека без имени бесполезен, и
    # ровно на этом 02.09 сломался `follow`.
    assert "HontoUKI" in said
    # И ни одного слова, которого роутер не измерял. «Ушёл» — факт, «бросил тебя» —
    # прочтение, и прочтение принадлежит ей, а не проводу.
    assert not re.search(
        r"\b(ignor\w+|abandon\w+|left you|lonely|misses?|loves?|scared|finally)\b",
        said, re.IGNORECASE,
    )


def test_an_unknown_event_still_gives_a_readable_note():
    # Роутер объявляет свои виды сам и может завести новый раньше, чем про него узнают
    # здесь. Пустая строка была бы ходом ни о чём; голое имя вида — честный минимум.
    assert _note({"kind": "something_new"}) == "[something_new]"


def test_only_the_gaze_waits_for_him_to_finish_speaking():
    """Пороги тишины: у поводов про него их почти нет, и это осмысленно.

    `QUIET_AFTER_HIM` защищает разговор от её собственных дел. Повод про него — сам
    разговор и есть, только не словами: ответить на подаренный алмаз через секунду
    после «take this» значит услышать, а не перебить.

    Взгляд — исключение: он может стоять и смотреть посреди беседы, и «ты на меня
    смотришь!» поверх его же реплики это ровно прежний дефект.
    """
    assert ABOUT_HIM["watched"] is None, "None значит держать общий порог"
    assert QUIET_AFTER_HIM > 0
    assert all(
        wait == 0.0 for kind, wait in ABOUT_HIM.items() if kind != "watched"
    )
