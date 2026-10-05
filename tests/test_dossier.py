"""The dossier: what a person did, between a turn's tag and a closeness stage.

Live 09.09 the player was rude four times in a row. The tags read correctly, the axes fell
0.935 → 0.797 — and all that time the stage stayed `devoted`, whose block says she is
completely defenceless. She went cold for exactly one turn and on the next occasion did not
know she had. The author's note: "my rudeness was not punished at all".

The cause was neither the numbers nor the classifier: between "this turn" and "are we close at
all" there was no layer that remembers DEEDS.
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
    """Ordinary conversation is not a deed.

    What counts as a deed is decided by the PACK through its `sentiment`, not by the engine's
    own ideas of what matters. Otherwise the dossier would pay tokens for the absence of events.
    """
    assert summarise(deeds(turns("mundane", "neutral", "on_your_own", "task"), pack)) == ""


def test_freshest_first_and_the_distance_is_named(pack):
    # Nine turns ago and just now are different news, and the second must not look like the
    # first. Distance is counted in turns, not minutes: a conversation has its own measure.
    found = deeds(turns("insult", "mundane", "mundane", "gift"), pack)
    assert [d.tag for d in found] == ["gift", "insult"]
    assert found[0].turns_ago == 0
    assert found[1].turns_ago == 3


def test_a_single_deed_is_not_counted_out_loud(pack):
    said = summarise(deeds(turns("insult"), pack))
    assert "x1" not in said, "'once' is a count, not speech"


def test_nothing_yet_is_an_empty_dossier(pack):
    assert summarise(deeds([], pack)) == ""
    assert summarise(deeds(None, pack)) == ""


def test_a_tag_the_pack_does_not_know_is_ignored(pack):
    """The pack may have been rewritten under an already lived transcript.

    A tag no longer in the pack is not a deed but a trace of an earlier edition, and the
    dossier must not fail on it.
    """
    said = summarise(deeds(turns("insult", "some_old_tag_from_a_previous_pack"), pack))
    assert "insult" in said
    assert "some_old_tag" not in said


def test_the_dossier_is_a_fact_and_never_a_reading(pack):
    """The engine names, the pack interprets.

    Whether she holds a grudge, laughs it off or does not notice at all is up to the pack. The
    same line along which the game port carries the world's words and does not read them.
    """
    said = summarise(deeds(turns("insult", "insult", "killed_by_him", "gift"), pack))
    for word in ("angry", "hurt", "forgive", "should", "deserve", "punish", "sorry"):
        assert word not in said.lower()


def test_the_list_stays_short(pack):
    # The line goes into the prompt EVERY turn; a list nobody reads to the end is a cost without a benefit.
    many = turns(
        "insult", "warmth", "gift", "watched", "praise_work",
        "teasing", "neglect", "someone_else", "killed_by_him",
    )
    assert len(deeds(many, pack, most=6)) == 6


def test_a_deed_falls_out_of_the_count_when_its_time_is_up(pack):
    """The dossier got a way out, and that was the main thing it lacked.

    Without a term it only grew: `insult x9` would weigh the same a hundred turns later — the
    very ratchet, "a fact had no way out", that Maria's line stood on for three days. The
    author's decision: a reference of terms for EACH kind of deed.
    """
    lifetime = pack.remembered_for["insult"]
    # One insult just now and one beyond the term — one is counted.
    old = turns("insult", *["mundane"] * lifetime, "insult")
    found = {d.tag: d for d in deeds(old, pack)}
    assert found["insult"].times == 1
    assert found["insult"].turns_ago == 0


def test_the_reference_is_per_tag_and_not_one_number(pack):
    """Deeds have different terms, and that is the point of the reference.

    Rudeness stops counting after a couple of dozen turns; a killing does not. One common term
    would make these two events the same.
    """
    assert pack.remembered_for["killed_by_him"] > pack.remembered_for["insult"] * 10
    far = turns("killed_by_him", *["mundane"] * 100)
    assert any(d.tag == "killed_by_him" for d in deeds(far, pack))
    # And rudeness at the same distance no longer counts.
    assert not any(d.tag == "insult" for d in deeds(turns("insult", *["mundane"] * 100), pack))


def test_a_tag_without_a_lifetime_gets_the_engine_default(pack):
    """The reference is optional: a pack that does not write it works as before."""
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
    """Three insults in a row and one a hundred turns ago are "three", not "four".

    The term is checked on each deed separately; otherwise one fresh case would resurrect the
    whole long-expired count.
    """
    rows = turns("insult", *["mundane"] * 100, "insult", "insult", "insult")
    found = {d.tag: d for d in deeds(rows, pack)}
    assert found["insult"].times == 3


def test_a_repeated_gift_is_worth_less_each_time(pack):
    """The author's note: one can simply shower her with gifts, especially in creative.

    The first diamond of an evening means "he thought of me", the twentieth "he emptied his
    pockets", and they cannot have one price. A rule without magic numbers: the N-th deed within
    its term is worth 1/N, and it never reaches zero — he did think of her.
    """
    assert worth(deeds([], pack), pack, "gift") == 1.0
    assert worth(deeds(turns("gift"), pack), pack, "gift") == 0.5
    assert worth(deeds(turns("gift", "gift", "gift"), pack), pack, "gift") == 0.25


def test_the_lifetime_gives_it_breathing_room(pack):
    """An hour later a gift is worth a whole one again.

    The count is kept within the memory term, and for a gift that is sixty turns. So gifts
    stop being a score and become a rhythm.
    """
    lifetime = pack.remembered_for["gift"]
    stale = turns("gift", *["mundane"] * (lifetime + 1))
    assert worth(deeds(stale, pack), pack, "gift") == 1.0


def test_rudeness_does_not_get_cheaper_with_repetition(pack):
    """And that is the character's choice, not an omission.

    The fifth insult of an evening must not be cheaper than the first: getting used to being
    spoken to like that is not the trait being built here.
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
