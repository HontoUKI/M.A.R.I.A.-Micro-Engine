"""Досье: что человек делал, между тегом хода и ступенью близости.

Живьём 09.09 игрок нагрубил четыре раза подряд. Теги прочлись верно, оси упали
0.935 → 0.797 — и ступень всё это время оставалась `devoted`, чей блок говорит, что она
совершенно безоружна. Она ушла в холод ровно на один ход и на следующем поводе не знала,
что уходила. Замечание автора: «моя грубость никак не наказалась».

Причина не в числах и не в классификаторе: между «этот ход» и «мы вообще близки» не было
слоя, который помнит ПОСТУПКИ.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from engine.dossier import deeds, summarise
from engine.pack import load_pack

_YUKINA = Path(__file__).resolve().parents[1] / "characters" / "yukina"


@pytest.fixture
def pack():
    return load_pack(str(_YUKINA))


def turns(*tags):
    return [{"tag": t} for t in tags]


def test_rudeness_is_remembered_and_counted(pack):
    said = summarise(turns("insult", "mundane", "insult", "warmth"), pack)
    assert "insult x2" in said
    assert "warmth" in said


def test_the_ordinary_hum_is_not_a_deed(pack):
    """Обычный разговор поступком не является.

    Что считать поступком, решает ПАК своим `sentiment`, а не движок своими
    представлениями о важном. Иначе досье платило бы токенами за отсутствие событий.
    """
    assert summarise(turns("mundane", "neutral", "on_your_own", "task"), pack) == ""


def test_freshest_first_and_the_distance_is_named(pack):
    # Девять ходов назад и только что — разные новости, и вторая не должна выглядеть
    # первой. Расстояние считается в ходах, а не в минутах: у разговора своя мера.
    found = deeds(turns("insult", "mundane", "mundane", "gift"), pack)
    assert [d.tag for d in found] == ["gift", "insult"]
    assert found[0].turns_ago == 0
    assert found[1].turns_ago == 3


def test_a_single_deed_is_not_counted_out_loud(pack):
    said = summarise(turns("insult"), pack)
    assert "x1" not in said, "«один раз» — это счёт, а не речь"


def test_nothing_yet_is_an_empty_dossier(pack):
    assert summarise([], pack) == ""
    assert summarise(None, pack) == ""


def test_a_tag_the_pack_does_not_know_is_ignored(pack):
    """Пак могли переписать под уже прожитой расшифровкой.

    Тег, которого в паке больше нет, — это не поступок, а след прошлой редакции, и
    падать на нём досье не должно.
    """
    said = summarise(turns("insult", "some_old_tag_from_a_previous_pack"), pack)
    assert "insult" in said
    assert "some_old_tag" not in said


def test_the_dossier_is_a_fact_and_never_a_reading(pack):
    """Движок называет, пак толкует.

    Злопамятна ли она, смеётся ли над этим или не замечает вовсе — решает пак. Та же
    граница, по которой игровой порт несёт слова мира и не читает их.
    """
    said = summarise(turns("insult", "insult", "killed_by_him", "gift"), pack)
    for word in ("angry", "hurt", "forgive", "should", "deserve", "punish", "sorry"):
        assert word not in said.lower()


def test_the_list_stays_short(pack):
    # Строка едет в промпт КАЖДЫЙ ход; список, который не дочитывают, — плата без выгоды.
    many = turns(
        "insult", "warmth", "gift", "watched", "praise_work",
        "teasing", "neglect", "someone_else", "killed_by_him",
    )
    assert len(deeds(many, pack, most=6)) == 6
