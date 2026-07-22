"""Scene runtime: one group-chat turn, end to end, against a stub LLM."""
from __future__ import annotations

import json

from engine.scene.matrix import RelationshipMatrix
from engine.scene.models import USER_ID, ScenePack
from engine.scene.runtime import SceneRuntime
from engine.scene.tags import ActorTagset
from tests._packs import make_pack


class SceneLLM:
    """Distinguishes the three call kinds by their JSON schema `fmt`:
    speaker-select (has 'speaker'), moment (has 'tag'+'target'), voice (fmt=None).
    """

    def __init__(self, *, speaker=None, tag="warmth", target=USER_ID, reply="Hi."):
        self.speaker = speaker
        self.tag = tag
        self.target = target
        self.reply = reply
        self.voice_prompts = []

    def chat(self, messages, *, model=None, fmt=None, options=None):
        if fmt is None:
            self.voice_prompts.append(messages)
            return self.reply
        props = fmt.get("properties", {})
        if "speaker" in props:
            return json.dumps({"speaker": self.speaker})
        return json.dumps({"tag": self.tag, "target": self.target})

    def embed(self, text, *, model=None):  # pragma: no cover - unused
        return [0.0]


def _two_actor_scene(**over) -> ScenePack:
    data = {
        "spec_version": 1,
        "meta": {
            "name": "s", "display_name": "S", "version": "0.1.0",
            "license": "x", "author": "y",
        },
        "setting": "A quiet cafe.",
        "cast": ["aria", "bram"],
        "director": "model",
    }
    data.update(over)
    return ScenePack.model_validate(data)


def _packs():
    aria = make_pack(meta={
        "name": "aria", "display_name": "Aria", "version": "0.1.0",
        "license": "x", "author": "y", "fallback_tag": "neutral",
        "description": "a calm librarian",
    })
    bram = make_pack(meta={
        "name": "bram", "display_name": "Bram", "version": "0.1.0",
        "license": "x", "author": "y", "fallback_tag": "neutral",
        "description": "a gruff baker",
    })
    return {"aria": aria, "bram": bram}


def _runtime(llm, scene=None, **kw):
    return SceneRuntime(scene or _two_actor_scene(), _packs(), llm, **kw)


# ---------------------------------------------------------------- basic turn


def test_turn_returns_speaker_reply_tag_and_target():
    llm = SceneLLM(speaker="aria", tag="warmth", target=USER_ID, reply="How nice.")
    rt = _runtime(llm)
    result = rt.advance("you're both lovely")
    assert result.speaker == "aria"
    assert result.reply == "How nice."
    assert result.tag == "warmth"
    assert result.target == USER_ID


def test_explicit_speaker_overrides_the_director():
    llm = SceneLLM(speaker="aria", reply="hm")  # director would pick aria
    rt = _runtime(llm)
    result = rt.advance("hello", speaker="bram")
    assert result.speaker == "bram"


def test_warmth_moves_only_the_speaker_to_target_edge():
    llm = SceneLLM(speaker="aria", tag="warmth", target=USER_ID)
    rt = _runtime(llm)
    rt.advance("you're great")
    # aria -> user moved by the warmth delta (+5 / +3 over 0 baseline).
    assert rt.matrix.feeling("aria", USER_ID).affection == 5
    # The reverse and unrelated edges are untouched (asymmetry holds).
    assert rt.matrix.feeling("bram", "aria").affection == 0
    assert rt.matrix.feeling("aria", "bram").affection == 0


def test_reaction_can_target_another_actor():
    llm = SceneLLM(speaker="aria", tag="warmth", target="bram")
    rt = _runtime(llm)
    result = rt.advance("Aria, what do you think of Bram?")
    assert result.target == "bram"
    assert rt.matrix.feeling("aria", "bram").affection == 5
    assert rt.matrix.feeling("aria", USER_ID).affection == 0


# ---------------------------------------------------------------- witness pass


class RoleAwareLLM:
    """Answers moment classification per acting actor, so the speaker and the
    witness can react differently in the same turn."""

    def __init__(self, *, speaker, by_actor, reply="ok"):
        self.speaker = speaker
        self.by_actor = by_actor  # actor id -> (tag, target)
        self.reply = reply

    def chat(self, messages, *, model=None, fmt=None, options=None):
        if fmt is None:
            return self.reply
        props = fmt.get("properties", {})
        if "speaker" in props:
            return json.dumps({"speaker": self.speaker})
        # Identify whose POV this classification is from via the system line.
        system = messages[0]["content"]
        for actor, (tag, target) in self.by_actor.items():
            if self._display(actor) in system.split("\n")[0]:
                return json.dumps({"tag": tag, "target": target})
        return json.dumps({"tag": "neutral", "target": USER_ID})

    @staticmethod
    def _display(actor):
        return {"aria": "Aria", "bram": "Bram"}[actor]

    def embed(self, text, *, model=None):  # pragma: no cover
        return [0.0]


def test_speaker_and_witness_react_independently_in_one_turn():
    # Aria (speaker) warms to the user; Bram (witness) records his own reaction.
    llm = RoleAwareLLM(
        speaker="aria",
        by_actor={"aria": ("warmth", USER_ID), "bram": ("teasing_not_a_tag", USER_ID)},
    )
    rt = _runtime(llm)
    result = rt.advance("Aria, you're wonderful")
    assert result.speaker == "aria"
    assert rt.matrix.feeling("aria", USER_ID).affection == 5  # first-hand, full
    # Bram's unknown tag falls back to neutral (no move) but he is still recorded
    # as having witnessed the turn.
    assert [w.actor for w in result.witnessed] == ["bram"]


def test_witness_positive_reaction_is_half_of_first_hand():
    llm = RoleAwareLLM(
        speaker="aria",
        by_actor={"aria": ("neutral", USER_ID), "bram": ("warmth", "aria")},
    )
    rt = _runtime(llm)
    result = rt.advance("hello you two")
    # Bram witnessed and warmed toward Aria at half strength: +5 -> +2.5.
    assert rt.matrix.feeling("bram", "aria").affection == 2.5
    assert rt.matrix.feeling("bram", "aria").trust == 1.5  # +3 -> 1.5
    w = result.witnessed[0]
    assert (w.actor, w.tag, w.target) == ("bram", "warmth", "aria")


def test_no_witness_reactions_in_a_solo_cast():
    scene = _two_actor_scene(cast=["aria"])
    llm = SceneLLM(speaker="aria", reply="alone here")
    rt = SceneRuntime(scene, _packs(), llm)
    assert rt.advance("hi").witnessed == ()


# ---------------------------------------------------------------- transcript


def test_user_and_reply_are_recorded_in_the_transcript():
    llm = SceneLLM(speaker="aria", reply="Welcome.")
    rt = _runtime(llm)
    rt.advance("hi everyone")
    assert [(line.speaker, line.content) for line in rt.transcript] == [
        (USER_ID, "hi everyone"),
        ("aria", "Welcome."),
    ]


def test_voice_prompt_pins_the_scene_setting_and_presence():
    llm = SceneLLM(speaker="aria", reply="x")
    rt = _runtime(llm)
    rt.advance("hello")
    system = llm.voice_prompts[0][0]["content"]
    assert "A quiet cafe." in system  # the shared setting is pinned
    assert "Bram" in system  # cast presence names the other actor
    assert "User" in system


# ---------------------------------------------------------------- director


def test_director_pick_is_used_when_no_explicit_speaker():
    llm = SceneLLM(speaker="bram", reply="Hmph.")
    rt = _runtime(llm)
    assert rt.advance("anyone there?").speaker == "bram"


def test_round_robin_fallback_when_director_returns_nothing():
    # speaker=None -> selector can't parse -> round-robin from the start.
    llm = SceneLLM(speaker=None, reply="...")
    rt = _runtime(llm)
    assert rt.advance("hi").speaker == "aria"  # first in cast


# ---------------------------------------------------------------- seams


def test_seeded_matrix_and_scenario_tag_collision():
    import pytest

    from engine.scene.errors import SceneValidationError

    # aria's base pack already has a 'warmth' tag; a scenario tag with that id
    # must be rejected at assembly.
    scene = _two_actor_scene(
        scenario_tags={"aria": [{"id": "warmth", "description": "dup"}]}
    )
    with pytest.raises(SceneValidationError, match="collides"):
        _runtime(SceneLLM(), scene=scene)


def test_missing_cast_pack_raises():
    import pytest

    scene = _two_actor_scene(cast=["aria", "ghost"])
    with pytest.raises(KeyError, match="not loaded"):
        SceneRuntime(scene, _packs(), SceneLLM())


def test_scenario_tag_available_only_in_window():
    # A high-gated scenario tag is hidden while the actor's standing is low.
    scene = _two_actor_scene(
        scenario_tags={
            "aria": [{"id": "special", "description": "d", "unlock_at": 0.8, "lock_at": 1.0}]
        }
    )
    tagset = ActorTagset.build(_packs()["aria"], scene.scenario_tags["aria"])
    assert "special" not in {t.id for t in tagset.available(0.1)}
    assert "special" in {t.id for t in tagset.available(0.9)}


def test_from_scene_matrix_is_used_when_not_injected():
    scene = _two_actor_scene(
        relationships=[{"from": "aria", "to": "bram", "affection": 20}]
    )
    rt = SceneRuntime(scene, _packs(), SceneLLM(speaker="aria", tag="neutral", target="bram"))
    assert isinstance(rt.matrix, RelationshipMatrix)
    assert rt.matrix.feeling("aria", "bram").affection == 20
