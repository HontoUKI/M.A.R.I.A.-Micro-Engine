"""Limits of what she does with her hands (§5 of the concept: delay, not take away).

Tag gates decide what she can feel; these decide what she can DO. The difference is not
cosmetic: a tag lives one turn, while a deed changes the world forever, and a killed
villager is not taken back by a stage or a mood.

What is checked here is narrowness, not the ban itself: a rule wider than its harm takes
away the very game all this was started for.
"""
from __future__ import annotations

import json
import re

import pytest

from engine.character import CharacterRuntime
from engine.hands import GamePort
from engine.pack.models import ActionBound
from engine.state import StateKernel
from tests._packs import make_pack


class _Says:
    """A model that always answers with the same `<play>` block."""

    def __init__(self, line: str, tag: str = "neutral") -> None:
        self._line = line
        self._tag = tag

    def chat(self, messages, *, model=None, fmt=None, options=None):
        return json.dumps({"tag": self._tag}) if fmt is not None else self._line


class _Hands(GamePort):
    """Hands that do nothing but remember what they were told."""

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

    def read(self, text):
        """The router reads the grammar (`POST /v0/read`); here only as much as these lines
        need: `verb(object)`, `verb(all: true)`, `verb(ALL EXCEPT [a, b])`."""
        steps = []
        for line in filter(None, (s.strip() for s in text.splitlines())):
            verb, arg = re.fullmatch(r"(\w+)\((.*)\)", line).groups()
            if arg.startswith("ALL"):
                spared = re.search(r"EXCEPT \[(.*)\]", arg)
                left = [w.strip() for w in spared.group(1).split(",")] if spared else []
                steps.append({"verb": verb, "where": {"select": {"mode": "all", "except": left}}})
            elif arg == "all: true":
                steps.append({"verb": verb, "where": {"all": True}})
            else:
                steps.append({"verb": verb, "object": arg})
        return {"steps": steps, "repeat": 1, "word": None}


def _pack(**more):
    return make_pack(stage_axis="bond", **more)


def _runtime(pack, line, *, bond: float, hands):
    state = StateKernel(pack.axes, values={"affection": 50.0, "trust": 50.0, "bond": bond})
    return CharacterRuntime(pack, _Says(line), state=state, hands=hands)


def test_a_pack_without_bounds_forbids_nothing():
    hands = _Hands()
    got = _runtime(_pack(), "sure.\n<play>\nfight(villager)\n</play>",
                   bond=0.0, hands=hands).respond("go on")
    assert got.did, "the engine decides nothing for the pack by itself"
    assert hands.taken


def test_never_means_never_however_close_she_is():
    """Food is not a delay. In a world where death is final, that is a different act."""
    pack = _pack(bounds=[
        ActionBound(verb="take_from", object=["bread"], never=True, refuse="he lives on that"),
    ])
    hands = _Hands()
    got = _runtime(pack, "ok.\n<play>\ntake_from(bread)\n</play>",
                   bond=100.0, hands=hands).respond("take the bread")
    assert got.did == ()
    assert hands.taken == [], "it never reached the hands"


def test_the_window_opens_on_the_stage_and_not_before():
    pack = _pack(bounds=[
        ActionBound(verb="fight", object=["villager"], unlock_at=0.75, refuse="not yet"),
    ])
    line = "fine.\n<play>\nfight(villager)\n</play>"

    early = _Hands()
    _runtime(pack, line, bond=50.0, hands=early).respond("kill them")
    assert early.taken == [], "at 0.50 the gates are closed"

    late = _Hands()
    _runtime(pack, line, bond=80.0, hands=late).respond("kill them")
    assert late.taken, "at 0.80 — her choice"


def test_only_the_named_thing_is_held_back():
    """One forbidden step does not cancel the whole decision."""
    pack = _pack(bounds=[ActionBound(verb="take_from", object=["bread"], never=True)])
    hands = _Hands()
    line = "ok.\n<play>\ntake_from(bread)\ntake_from(diamond)\n</play>"
    got = _runtime(pack, line, bond=0.0, hands=hands).respond("clear the chest")
    assert len(hands.taken) == 1
    assert [g.verb for g in hands.taken[0].steps] == ["take_from"]
    assert hands.taken[0].steps[0].fields["object"] == "diamond"
    assert got.did


def test_taking_EVERYTHING_is_covered_by_the_bound():
    """Otherwise the limit is bypassed with one word: `where.all` names not a single item."""
    pack = _pack(bounds=[ActionBound(verb="take_from", object=["bread"], never=True)])
    hands = _Hands()
    got = _runtime(pack, "ok.\n<play>\ntake_from(all: true)\n</play>",
                   bond=0.0, hands=hands).respond("take it all")
    assert hands.taken == []
    assert got.did == ()


def test_a_selection_is_everything_unless_the_forbidden_is_left_out():
    """`take_from(ALL …)` names no things, and what falls into it the world decides at the moment of
    the step.

    So a selection is "everything", like `where.all`: otherwise "never take his bread" is
    bypassed by the word ALL. The way out is narrow and her own: leave the bread behind
    EXCEPT (28.09).
    """
    pack = _pack(bounds=[
        ActionBound(verb="take_from", object=["bread"], never=True, refuse="he lives on that"),
    ])
    grabbed = _Hands()
    runtime = _runtime(pack, "ok.\n<play>\ntake_from(ALL)\n</play>", bond=100.0, hands=grabbed)
    assert runtime.respond("take it all").did == ()
    assert grabbed.taken == []
    assert "leave it out with EXCEPT" in runtime._game_block()

    spared = _Hands()
    _runtime(pack, "ok.\n<play>\ntake_from(ALL EXCEPT [bread, apple])\n</play>",
             bond=0.0, hands=spared).respond("take the rest")
    assert spared.taken, "the bread is left — the limit is not about this step"


def test_a_neighbouring_verb_is_not_touched():
    pack = _pack(bounds=[ActionBound(verb="take_from", object=["bread"], never=True)])
    hands = _Hands()
    _runtime(pack, "ok.\n<play>\ngather(bread)\n</play>",
             bond=0.0, hands=hands).respond("get bread")
    assert hands.taken, "the limit is about the chest, not about the word 'bread'"


def test_never_cannot_be_a_window_in_disguise():
    with pytest.raises(ValueError):
        ActionBound(verb="take_from", never=True, unlock_at=0.99)


def test_she_is_TOLD_what_she_did_not_do():
    """A silently dropped step she reads as a breakage and writes the same line again.

    That already happened with unread lines on 03.09, and the cure is the same: tell her.
    Without this check the limit would be built and never reach the turn — that very recurring
    shape.
    """
    pack = _pack(bounds=[
        ActionBound(verb="take_from", object=["bread"], never=True, refuse="he lives on that"),
    ])
    hands = _Hands()
    runtime = _runtime(pack, "ok.\n<play>\ntake_from(bread)\n</play>",
                       bond=0.0, hands=hands)
    runtime.respond("take the bread")

    block = runtime._game_block()
    assert "did not do this" in block
    assert "he lives on that" in block, "a reason, not a bare refusal"

    # And said ONCE: a complaint that outlives its turn becomes noise about the past.
    assert "did not do this" not in runtime._game_block()
