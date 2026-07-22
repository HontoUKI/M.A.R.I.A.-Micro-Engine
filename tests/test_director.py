"""Speaker selection — model-directed pick and round-robin fallback."""
from __future__ import annotations

import json

from engine.llm import LLMError
from engine.scene.director import SpeakerSelector, next_round_robin


class ScriptedLLM:
    def __init__(self, answers):
        self._answers = list(answers)
        self.formats = []

    def chat(self, messages, *, model=None, fmt=None, options=None):
        self.formats.append(fmt)
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def embed(self, text, *, model=None):  # pragma: no cover - unused
        return [0.0]


def test_chooses_a_valid_cast_member():
    llm = ScriptedLLM([json.dumps({"speaker": "kaguya"})])
    pick = SpeakerSelector(llm).choose(["megumin", "kaguya"], "", "you're both here")
    assert pick == "kaguya"


def test_enum_is_constrained_to_the_cast():
    llm = ScriptedLLM([json.dumps({"speaker": "megumin"})])
    SpeakerSelector(llm).choose(["megumin", "kaguya"], "ctx", "hi")
    assert llm.formats[0]["properties"]["speaker"]["enum"] == ["megumin", "kaguya"]


def test_unknown_pick_retries_then_returns_none():
    llm = ScriptedLLM(
        [json.dumps({"speaker": "ghost"}), json.dumps({"speaker": "also_ghost"})]
    )
    pick = SpeakerSelector(llm, max_retries=1).choose(["megumin", "kaguya"], "", "hi")
    assert pick is None
    assert len(llm.formats) == 2


def test_unparseable_returns_none():
    llm = ScriptedLLM(["not json", "still not json"])
    assert SpeakerSelector(llm, max_retries=1).choose(["a", "b"], "", "x") is None


def test_llm_error_returns_none_without_crashing():
    llm = ScriptedLLM([LLMError("down")])
    assert SpeakerSelector(llm).choose(["a", "b"], "", "x") is None


def test_single_actor_is_returned_without_a_model_call():
    llm = ScriptedLLM([])  # would IndexError if called
    assert SpeakerSelector(llm).choose(["solo"], "", "x") == "solo"


def test_empty_cast_returns_none():
    llm = ScriptedLLM([])
    assert SpeakerSelector(llm).choose([], "", "x") is None


# ---------------------------------------------------------------- round robin


def test_round_robin_wraps():
    cast = ["a", "b", "c"]
    assert next_round_robin(cast, None) == "a"
    assert next_round_robin(cast, "a") == "b"
    assert next_round_robin(cast, "c") == "a"  # wrap
    assert next_round_robin(cast, "unknown") == "a"
