"""The loop: a story that outlives the world (pack section `loop`, engine/loop.py).

A tag arms it; the next DIFFERENT world is a new try and steps the hidden counter.
It never reaches a client, a relationship reset does not touch it, and only
deleting the session's data clears it.
"""
from __future__ import annotations

import json

import pytest

from app.contracts import ChatMessage
from app.service import EngineService
from engine.loop import LoopCounter
from engine.registry import PackRegistry
from tests._packs import make_pack

LOOP = {
    "arm_on": ["hostility"],
    "steps": [{"block": "STEP ONE"}, {"block": "STEP TWO"}, {"block": "STEP LAST"}],
}


class Voice:
    """Tags every turn as `self.tag`; keeps the last voice prompt."""

    def __init__(self) -> None:
        self.tag = "neutral"
        self.system = ""

    def chat(self, messages, *, model=None, fmt=None, options=None):
        if fmt is not None:
            return json.dumps({"tag": self.tag})
        self.system = "\n".join(str(m.get("content", "")) for m in messages)
        return "ok"

    def embed(self, text, *, model=None):  # pragma: no cover - memory off here
        return [0.0]


@pytest.fixture
def world(tmp_path):
    pack = make_pack(loop=LOOP)
    voice = Voice()
    service = EngineService(
        registry=PackRegistry({pack.meta.name: pack}), llm=voice, sessions_dir=str(tmp_path)
    )

    def turn(world_id: str | None, tag: str = "neutral"):
        voice.tag = tag
        return service.complete(
            "aria", [ChatMessage(role="user", content="hi")], session_key="s", world=world_id
        )

    return service, voice, turn, tmp_path


def test_nothing_happens_before_it_is_armed():
    pack = make_pack(loop=LOOP)
    counter = LoopCounter()
    assert counter.entered("w1") is False
    assert counter.entered("w2") is False, "a new world without the arming tag is just a world"
    assert counter.block(pack) == ""


def test_armed_then_a_new_world_is_a_step_and_the_same_world_is_not():
    pack = make_pack(loop=LOOP)
    counter = LoopCounter()
    counter.entered("w1")
    counter.after("hostility", pack)
    assert counter.entered("w1") is False, "the router restarted in the same world"
    assert counter.entered("w2") is True
    assert (counter.count, counter.armed, counter.block(pack)) == (1, False, "STEP ONE")
    assert counter.entered(None) is False, "no fingerprint is no news"


def test_the_last_step_covers_every_later_try():
    pack = make_pack(loop=LOOP)
    counter = LoopCounter(count=7)
    assert counter.block(pack) == "STEP LAST"


def test_a_pack_cannot_arm_on_a_tag_it_does_not_have():
    with pytest.raises(ValueError):
        make_pack(loop={"arm_on": ["grief"], "steps": [{"block": "x"}]})


def test_the_step_reaches_her_prompt_and_never_the_client(world):
    service, voice, turn, _ = world
    turn("w1")
    turn("w1", tag="hostility")
    assert "STEP ONE" not in voice.system
    result = turn("w2")
    assert "STEP ONE" in voice.system
    assert "loop" not in json.dumps(result.__dict__, default=str).lower()


def test_a_relationship_reset_does_not_undo_it(world):
    service, voice, turn, tmp_path = world
    turn("w1", tag="hostility")
    turn("w2")
    service.reset_relationship("aria", "s")
    turn("w2")
    assert "STEP ONE" in voice.system, "irreversible: only deleting the session clears it"
    (next(tmp_path.glob("s__aria")) / "loop.json").unlink()
    turn("w3")
    assert "STEP ONE" not in voice.system
