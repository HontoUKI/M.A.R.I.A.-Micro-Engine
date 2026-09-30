"""Очередь подобранного: двадцать подборов — один ход, а не двадцать «спасибо».

Живьём 30.09 после его смерти она подбирала его вещи с места на место, и каждый подбор
был своим ходом. Очередь живёт `GIFTS_LIVE` секунд: заговорил он — всё едет в его ход,
промолчал — уходит одним поводом. Подарок и его посмертные вещи — разные факты, и
очередь их не смешивает.
"""
from __future__ import annotations

import threading

from tools.play import (
    DANGER_HOLD,
    GIFTS_LIVE,
    WITH_CONTENT,
    Gifts,
    _note,
    _ticking,
    _with_gifts,
    calm_now,
)


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


def given(who: str, *what: str, kind: str = "given") -> dict:
    return {"kind": kind, "who": who, "took": [{"what": w, "count": 1} for w in what]}


def test_pickups_are_held_and_let_out_once_folded():
    clock, gifts = Clock(), Gifts()
    stream = [given("HontoUKI", "torch"), given("HontoUKI", "torch", "cgs:revolver"), None]
    assert list(_with_gifts(iter(stream), gifts, clock)) == [], "nothing is said while it lives"

    clock.now += GIFTS_LIVE
    assert list(_with_gifts(iter([None]), gifts, clock)) == [
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
    assert gifts.take("HontoUKI") == [
        {"kind": "given", "who": "HontoUKI", "took": [{"what": "water_bucket", "count": 1}],
         "folded": True},
    ]
    clock.now += GIFTS_LIVE
    assert gifts.due(clock()) == []
    assert gifts.take("HontoUKI") == []


def test_other_events_pass_and_people_queue_apart():
    clock, gifts = Clock(), Gifts()
    heard = {"kind": "heard", "who": "HontoUKI", "said": "take it"}
    out = list(_with_gifts(iter([given("A", "stick"), heard, given("B", "dirt")]), gifts, clock))
    assert out == [heard]
    assert [one["took"] for one in gifts.take("B")] == [[{"what": "dirt", "count": 1}]]
    assert [one["took"] for one in gifts.take("A")] == [[{"what": "stick", "count": 1}]]


def test_the_lifetime_counts_from_the_first_pickup():
    clock, gifts = Clock(), Gifts()
    gifts.add("A", [{"what": "stick"}], clock())
    clock.now += GIFTS_LIVE - 1
    gifts.add("A", [{"what": "stick"}], clock())
    clock.now += 1
    assert [one["took"] for one in gifts.due(clock())] == [[{"what": "stick", "count": 2}]]


def test_his_things_after_death_are_not_a_gift_and_never_mixed_with_one():
    clock, gifts = Clock(), Gifts()
    stream = [given("HontoUKI", "torch"), given("HontoUKI", "gold_ingot", kind="picked_up_his")]
    list(_with_gifts(iter(stream), gifts, clock))
    held = gifts.take("HontoUKI")
    assert sorted(one["kind"] for one in held) == ["given", "picked_up_his"]
    his = next(one for one in held if one["kind"] == "picked_up_his")
    note = _note(his)
    assert "gave you" not in note, "he gave nothing"
    assert note == "[HontoUKI died; you picked up the things he dropped: gold_ingot]"
    assert WITH_CONTENT["picked_up_his"] == 0.0


def test_calm_occasions_wait_while_she_runs_and_danger_does_not():
    fled_at = 1000.0
    assert calm_now({"kind": "noticed"}, fled_at, fled_at + 3) is True
    assert calm_now({"kind": "progress", "came_upon": "x"}, fled_at, fled_at + 3) is True
    assert calm_now({"kind": "noticed"}, fled_at, fled_at + DANGER_HOLD) is False, "it passes"
    assert calm_now({"kind": "fled"}, fled_at, fled_at + 1) is False, "the chase itself speaks"
    assert calm_now({"kind": "died"}, fled_at, fled_at + 1) is False
    assert calm_now({"kind": "noticed"}, 0.0, fled_at) is False, "never fled — nothing held"


def test_a_silent_stream_still_ticks():
    hold = threading.Event()

    def quiet():
        yield {"kind": "heard"}
        hold.wait(5)

    ticks = _ticking(quiet(), every=0.05)
    assert next(ticks) == {"kind": "heard"}
    assert next(ticks) is None, "no event for a while is a tick, not a hang"
    hold.set()
