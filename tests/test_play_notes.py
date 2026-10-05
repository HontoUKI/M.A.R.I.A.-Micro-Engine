"""A world note about a person nearby: what exactly she reads.

The router reports a FACT — "gave", "is watching", "left", "something crept up on him" —
and the note must carry it in words without drawing a conclusion for her. Both are checked
here: that the content arrives whole and that there is no judgement in it.

The event shapes are not mine: the adapter declares them, the table is in its `minecraft/README.md`.
Erring here looks cheap and is costly in practice — a field taken NEXT to the right one gives a
note that looks correct and is always empty.
"""
from __future__ import annotations

import re

import pytest

from tools.play import QUIET_AFTER_HIM, WITH_CONTENT, _note, about_whom


def test_a_gift_says_who_and_what():
    said = _note({
        "kind": "given", "who": "HontoUKI",
        "took": [{"what": "diamond", "count": 2}, {"what": "iron_helmet", "count": 1}],
    })
    assert said == "[HontoUKI gave you diamond x2, iron_helmet]"
    # One is not written: "iron_helmet x1" is a count, not speech.
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
    # Left on foot — that is distance and time.
    walked = _note({"kind": "left", "who": "HontoUKI", "blocks": 63, "gone_for": 31})
    assert "63" in walked and "31" in walked
    # Logged out of the game is something else, and "63 blocks" here would be invention.
    out = _note({"kind": "left", "who": "HontoUKI", "why": "logged out"})
    assert out == "[HontoUKI logged out]"
    assert "blocks" not in out


def test_standing_with_others_names_them_and_counts_them():
    said = _note({
        "kind": "beside", "who": "HontoUKI",
        "them": [{"what": "villager", "count": 3}, {"what": "cow", "count": 1}],
    })
    assert said == "[HontoUKI is standing with villager x3, cow]"
    # A cow and a villager arrive alike: which of them is a rival is decided by the pack, not the wire.
    assert "villager" in said and "cow" in said


def test_danger_names_what_and_how_close():
    said = _note({"kind": "at_risk", "who": "HontoUKI", "from": "creeper", "blocks": 2})
    assert said == "[a creeper is 2 blocks from HontoUKI]"


@pytest.mark.parametrize("event", [
    {"kind": "given", "who": "HontoUKI", "took": [{"what": "diamond", "count": 1}]},
    {"kind": "watched", "who": "HontoUKI", "watching_for": 9, "while_working": True},
    {"kind": "left", "who": "HontoUKI", "blocks": 63, "gone_for": 31},
    {"kind": "returned", "who": "HontoUKI", "blocks": 9},
    {"kind": "at_risk", "who": "HontoUKI", "from": "creeper", "blocks": 2},
    {"kind": "beside", "who": "HontoUKI", "them": [{"what": "villager", "count": 3}]},
    {"kind": "died", "by_player": "HontoUKI", "how": "Yukina was slain by HontoUKI"},
])
def test_a_note_states_a_fact_and_never_a_reading(event):
    said = _note(event)
    # In brackets, like everything that does not come from a person: otherwise a note is indistinguishable from speech.
    assert said.startswith("[") and said.endswith("]")
    # The person's name is always named — a verb about a person without a name is useless, and
    # exactly this broke `follow` on 02.09.
    assert "HontoUKI" in said
    # And not one word the router did not measure. "Left" is a fact, "abandoned you" is a
    # reading, and the reading belongs to her, not the wire.
    assert not re.search(
        r"\b(ignor\w+|abandon\w+|left you|lonely|misses?|loves?|scared|finally)\b",
        said, re.IGNORECASE,
    )


def test_death_says_whether_a_person_did_it():
    """'She died' and 'YOU killed her' are different news, and the second must not be lost.

    The router asks the game itself about it and names the person in a separate field; the note
    only does not lose it. What a death by his hand means — rage, devotion or nothing — she
    decides.
    """
    by_him = _note({"kind": "died", "by_player": "HontoUKI",
                    "how": "Yukina was slain by HontoUKI"})
    by_world = _note({"kind": "died", "how": "Yukina was blown up by a creeper"})
    assert by_him == "[HontoUKI killed you]"
    assert "creeper" in by_world and "killed you" not in by_world
    # And a death without an explanation is still a death, not an empty bracket.
    assert _note({"kind": "died"}) == "[you died]"


def test_an_unknown_event_still_gives_a_readable_note():
    # The router declares its kinds itself and may start a new one before it is known about
    # here. An empty line would be a turn about nothing; the bare kind name is an honest minimum.
    assert _note({"kind": "something_new"}) == "[something_new]"


def test_only_the_gaze_waits_for_him_to_finish_speaking():
    """Quiet thresholds: occasions about him have almost none, and that makes sense.

    `QUIET_AFTER_HIM` protects the conversation from her own business. An occasion about him is
    the conversation itself, only not in words: answering a gifted diamond a second after
    "take this" is hearing him, not interrupting.

    A gaze is the exception: he may stand and look in the middle of a conversation, and "you're
    looking at me!" over his own line is exactly the old defect.
    """
    assert WITH_CONTENT["watched"] is None, "None means keep the common threshold"
    assert QUIET_AFTER_HIM > 0
    # 30.09: what she noticed far off, and a place that brings something back, wait too —
    # her news, not his deed.
    assert WITH_CONTENT["noticed"] is None and WITH_CONTENT["remembered"] is None
    assert all(
        wait == 0.0
        for kind, wait in WITH_CONTENT.items()
        if kind not in ("watched", "noticed", "remembered")
    )


def test_a_death_belongs_to_the_person_who_caused_it():
    """Live 09.09, and it cost dearly.

    He killed her, and the turn went into a conversation WITH HERSELF: `died` has no `who`
    field — the person lies in `by_player` — the loop had just restarted, and the fallback was
    HER name. A second ledger `minecraft:Yukina` appeared with a single row, where the −8 trust
    went. He killed her, and it cost him nothing; and a turn later she did not remember it,
    because the note lay in another window.
    """
    assert about_whom({"kind": "died", "by_player": "HontoUKI"}) == "HontoUKI"
    # A death to the world does not become anyone's: attributing it to a person would mean
    # charging him for the creeper.
    assert about_whom({"kind": "died", "how": "blown up by a creeper"}) == ""


def test_a_note_about_a_person_is_a_turn_about_that_person():
    for kind in ("given", "watched", "left", "returned", "beside", "at_risk"):
        assert about_whom({"kind": kind, "who": "HontoUKI"}) == "HontoUKI"


def test_her_own_work_belongs_to_nobody_by_itself():
    """A turn about her own furnace is not about a person, and there is nothing to invent one with.

    It goes to whoever she is talking to; and if she talks to nobody there is no turn at all.
    There is no conversation with oneself, and a ledger belonging to nobody silently eats what
    should have cost someone something.
    """
    for kind in ("closed", "waiting", "interrupted"):
        assert about_whom({"kind": kind}) == ""


def test_a_place_that_brings_something_back_is_named_with_when():
    """30.09: "Stop. She remembers we almost died here." The router says what and
    when; the note says it as a fact, never as a feeling."""
    said = _note({"kind": "remembered", "what": "something hit you here — skeleton",
                  "ago": "35 min ago", "times": 2, "blocks": 4})
    assert said.startswith("[you are back where this happened: something hit you here")
    assert "35 min ago" in said and "2 times" in said
    once = _note({"kind": "remembered", "what": "you died here", "ago": "2 h ago", "times": 1})
    assert "times" not in once


def test_his_death_is_told_in_the_game_s_own_words():
    note = _note({
        "kind": "player_died", "who": "HontoUKI",
        "how": "HontoUKI was slain by Ghost", "hardcore": True,
    })
    assert note == (
        "[HontoUKI died: HontoUKI was slain by Ghost"
        " — this world is hardcore, a death here is final]"
    )
    assert _note({"kind": "player_died", "who": "HontoUKI"}) == "[HontoUKI died]"
    assert about_whom({"kind": "player_died", "who": "HontoUKI"}) == "HontoUKI"
    assert WITH_CONTENT["player_died"] == 0.0, "his death does not wait for a pause"
