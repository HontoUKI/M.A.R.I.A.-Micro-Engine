"""Очередь подобранного: двадцать подборов — один ход, а не двадцать «спасибо».

Живьём 30.09 после его смерти она подбирала его вещи с места на место, и каждый подбор
был своим ходом. Очередь живёт `GIFTS_LIVE` секунд: заговорил он — всё едет в его ход,
промолчал — уходит одним поводом.
"""
from __future__ import annotations

from tools.play import GIFTS_LIVE, Gifts, _with_gifts


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def given(who: str, *what: str) -> dict:
    return {"kind": "given", "who": who, "took": [{"what": w, "count": 1} for w in what]}


def test_pickups_are_held_and_let_out_once_folded():
    clock, gifts = Clock(), Gifts()
    stream = [given("HontoUKI", "torch"), given("HontoUKI", "torch", "cgs:revolver"), None]
    out = []
    for event in _with_gifts(iter(stream), gifts, clock):
        out.append(event)
    assert out == [], "nothing is said while the queue lives"

    clock.now += GIFTS_LIVE
    out = list(_with_gifts(iter([None]), gifts, clock))
    assert out == [
        {
            "kind": "given",
            "who": "HontoUKI",
            "took": [{"what": "torch", "count": 2}, {"what": "cgs:revolver", "count": 1}],
            "folded": True,
        }
    ]
    assert list(_with_gifts(iter([None]), gifts, clock)) == [], "let out once"


def test_when_he_talks_the_queue_is_his_and_gone():
    clock, gifts = Clock(), Gifts()
    list(_with_gifts(iter([given("HontoUKI", "water_bucket")]), gifts, clock))
    assert gifts.take("HontoUKI") == [{"what": "water_bucket", "count": 1}]
    clock.now += GIFTS_LIVE
    assert gifts.due(clock()) == []
    assert gifts.take("HontoUKI") is None


def test_other_events_pass_and_people_queue_apart():
    clock, gifts = Clock(), Gifts()
    heard = {"kind": "heard", "who": "HontoUKI", "said": "take it"}
    out = list(_with_gifts(iter([given("A", "stick"), heard, given("B", "dirt")]), gifts, clock))
    assert out == [heard]
    assert gifts.take("B") == [{"what": "dirt", "count": 1}]
    assert gifts.take("A") == [{"what": "stick", "count": 1}]


def test_the_lifetime_counts_from_the_first_pickup():
    clock, gifts = Clock(), Gifts()
    gifts.add("A", [{"what": "stick"}], clock())
    clock.now += GIFTS_LIVE - 1
    gifts.add("A", [{"what": "stick"}], clock())
    clock.now += 1
    assert gifts.due(clock()) == [("A", [{"what": "stick", "count": 2}])]


def test_a_silent_stream_still_ticks():
    import threading

    from tools.play import _ticking

    hold = threading.Event()

    def quiet():
        yield {"kind": "heard"}
        hold.wait(5)

    ticks = _ticking(quiet(), every=0.05)
    assert next(ticks) == {"kind": "heard"}
    assert next(ticks) is None, "no event for a while is a tick, not a hang"
    hold.set()
