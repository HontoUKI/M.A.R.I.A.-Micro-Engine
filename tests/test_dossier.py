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

from engine.dossier import REMEMBERED_FOR, deeds, summarise, worth
from engine.pack import load_pack

_YUKINA = Path(__file__).resolve().parents[1] / "characters" / "yukina"


@pytest.fixture
def pack():
    return load_pack(str(_YUKINA))


def turns(*tags):
    return [{"tag": t} for t in tags]


def test_rudeness_is_remembered_and_counted(pack):
    said = summarise(deeds(turns("insult", "mundane", "insult", "warmth"), pack))
    assert "insult x2" in said
    assert "warmth" in said


def test_the_ordinary_hum_is_not_a_deed(pack):
    """Обычный разговор поступком не является.

    Что считать поступком, решает ПАК своим `sentiment`, а не движок своими
    представлениями о важном. Иначе досье платило бы токенами за отсутствие событий.
    """
    assert summarise(deeds(turns("mundane", "neutral", "on_your_own", "task"), pack)) == ""


def test_freshest_first_and_the_distance_is_named(pack):
    # Девять ходов назад и только что — разные новости, и вторая не должна выглядеть
    # первой. Расстояние считается в ходах, а не в минутах: у разговора своя мера.
    found = deeds(turns("insult", "mundane", "mundane", "gift"), pack)
    assert [d.tag for d in found] == ["gift", "insult"]
    assert found[0].turns_ago == 0
    assert found[1].turns_ago == 3


def test_a_single_deed_is_not_counted_out_loud(pack):
    said = summarise(deeds(turns("insult"), pack))
    assert "x1" not in said, "«один раз» — это счёт, а не речь"


def test_nothing_yet_is_an_empty_dossier(pack):
    assert summarise(deeds([], pack)) == ""
    assert summarise(deeds(None, pack)) == ""


def test_a_tag_the_pack_does_not_know_is_ignored(pack):
    """Пак могли переписать под уже прожитой расшифровкой.

    Тег, которого в паке больше нет, — это не поступок, а след прошлой редакции, и
    падать на нём досье не должно.
    """
    said = summarise(deeds(turns("insult", "some_old_tag_from_a_previous_pack"), pack))
    assert "insult" in said
    assert "some_old_tag" not in said


def test_the_dossier_is_a_fact_and_never_a_reading(pack):
    """Движок называет, пак толкует.

    Злопамятна ли она, смеётся ли над этим или не замечает вовсе — решает пак. Та же
    граница, по которой игровой порт несёт слова мира и не читает их.
    """
    said = summarise(deeds(turns("insult", "insult", "killed_by_him", "gift"), pack))
    for word in ("angry", "hurt", "forgive", "should", "deserve", "punish", "sorry"):
        assert word not in said.lower()


def test_the_list_stays_short(pack):
    # Строка едет в промпт КАЖДЫЙ ход; список, который не дочитывают, — плата без выгоды.
    many = turns(
        "insult", "warmth", "gift", "watched", "praise_work",
        "teasing", "neglect", "someone_else", "killed_by_him",
    )
    assert len(deeds(many, pack, most=6)) == 6


def test_a_deed_falls_out_of_the_count_when_its_time_is_up(pack):
    """У досье появился выход, и это было главным, чего ему не хватало.

    Без срока оно только росло: `insult x9` весило бы одинаково и через сотню ходов —
    тот самый храповик, «у факта не было выхода», на котором линия Марии простояла трое
    суток. Решение автора: справочник сроков на КАЖДЫЙ род поступка.
    """
    lifetime = pack.remembered_for["insult"]
    # Одна грубость только что и одна за пределами срока — считается одна.
    old = turns("insult", *["mundane"] * lifetime, "insult")
    found = {d.tag: d for d in deeds(old, pack)}
    assert found["insult"].times == 1
    assert found["insult"].turns_ago == 0


def test_the_reference_is_per_tag_and_not_one_number(pack):
    """Сроки у поступков разные, и в этом смысл справочника.

    Грубость перестаёт считаться через два десятка ходов; убийство через два десятка не
    перестаёт. Один общий срок сделал бы эти два события одинаковыми.
    """
    assert pack.remembered_for["killed_by_him"] > pack.remembered_for["insult"] * 10
    far = turns("killed_by_him", *["mundane"] * 100)
    assert any(d.tag == "killed_by_him" for d in deeds(far, pack))
    # А грубость на том же расстоянии уже не считается.
    assert not any(d.tag == "insult" for d in deeds(turns("insult", *["mundane"] * 100), pack))


def test_a_tag_without_a_lifetime_gets_the_engine_default(pack):
    """Справочник необязателен: пак, который его не пишет, работает как раньше."""
    class _Bare:
        tags = pack.tags
        remembered_for = {}

        @staticmethod
        def tag(name):
            return pack.tag(name)

    inside = turns("insult", *["mundane"] * (REMEMBERED_FOR - 2))
    outside = turns("insult", *["mundane"] * (REMEMBERED_FOR + 2))
    assert any(d.tag == "insult" for d in deeds(inside, _Bare))
    assert not any(d.tag == "insult" for d in deeds(outside, _Bare))


def test_the_lifetime_is_checked_on_each_deed_not_on_the_kind(pack):
    """Три грубости подряд и одна сто ходов назад — это «три», а не «четыре».

    Срок сверяется на каждом поступке отдельно; иначе один свежий случай воскрешал бы
    весь давно истёкший счёт.
    """
    rows = turns("insult", *["mundane"] * 100, "insult", "insult", "insult")
    found = {d.tag: d for d in deeds(rows, pack)}
    assert found["insult"].times == 3


def test_a_repeated_gift_is_worth_less_each_time(pack):
    """Замечание автора: подарками можно просто задарить, особенно из креатива.

    Первый алмаз за вечер значит «он обо мне подумал», двадцатый — «он вытряхнул карманы»,
    и цена у них не может быть одна. Правило без магических чисел: N-й поступок в пределах
    своего срока стоит 1/N, и до нуля не доходит никогда — он всё-таки подумал.
    """
    assert worth(deeds([], pack), pack, "gift") == 1.0
    assert worth(deeds(turns("gift"), pack), pack, "gift") == 0.5
    assert worth(deeds(turns("gift", "gift", "gift"), pack), pack, "gift") == 0.25


def test_the_lifetime_gives_it_breathing_room(pack):
    """Через час подарок снова стоит целого.

    Счёт ведётся в пределах срока памяти, а он у подарка шестьдесят ходов. Значит подарки
    перестают быть счётом и становятся ритмом.
    """
    lifetime = pack.remembered_for["gift"]
    stale = turns("gift", *["mundane"] * (lifetime + 1))
    assert worth(deeds(stale, pack), pack, "gift") == 1.0


def test_rudeness_does_not_get_cheaper_with_repetition(pack):
    """И это выбор характера, а не упущение.

    Пятое оскорбление за вечер не должно быть дешевле первого: привыкать к тому, что с
    тобой так разговаривают, — не та черта, которую здесь строят.
    """
    assert "insult" not in pack.diminishing
    assert worth(deeds(turns("insult", "insult", "insult"), pack), pack, "insult") == 1.0


def test_a_pack_that_declares_nothing_keeps_full_price(pack):
    class _Bare:
        tags = pack.tags
        remembered_for = {}
        diminishing = []

        @staticmethod
        def tag(name):
            return pack.tag(name)

    assert worth(deeds(turns("gift", "gift"), _Bare), _Bare, "gift") == 1.0
