"""Tag classifier contracts against a stub LLM."""
from __future__ import annotations

import json

from engine.llm import LLMError
from engine.perception import TagClassifier
from tests._packs import make_pack


class ScriptedLLM:
    """Returns queued chat answers; records the format passed each call."""

    def __init__(self, answers):
        self._answers = list(answers)
        self.formats = []

    def chat(self, messages, *, model=None, fmt=None, options=None):
        self.formats.append(fmt)
        if not self._answers:
            raise AssertionError("unexpected extra chat call")
        answer = self._answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    def embed(self, text, *, model=None):  # pragma: no cover - unused here
        return [0.0]


def test_valid_tag_is_returned():
    llm = ScriptedLLM([json.dumps({"tag": "warmth"})])
    tag = TagClassifier(llm).classify(make_pack(), "you're lovely")
    assert tag == "warmth"


def test_schema_constrains_to_declared_tag_enum():
    llm = ScriptedLLM([json.dumps({"tag": "neutral"})])
    TagClassifier(llm).classify(make_pack(), "hi")
    schema = llm.formats[0]
    assert schema["properties"]["tag"]["enum"] == ["warmth", "hostility", "neutral"]


def test_unknown_tag_retries_then_falls_back():
    llm = ScriptedLLM(
        [json.dumps({"tag": "not_a_tag"}), json.dumps({"tag": "still_wrong"})]
    )
    tag = TagClassifier(llm, max_retries=1).classify(make_pack(), "hi")
    assert tag == "neutral"  # meta.fallback_tag
    assert len(llm.formats) == 2  # original + one retry


def test_unparseable_answer_falls_back():
    llm = ScriptedLLM(["this is not json", "also not json"])
    tag = TagClassifier(llm, max_retries=1).classify(make_pack(), "hi")
    assert tag == "neutral"


def test_second_attempt_can_recover():
    llm = ScriptedLLM(["garbage", json.dumps({"tag": "hostility"})])
    tag = TagClassifier(llm, max_retries=1).classify(make_pack(), "go away")
    assert tag == "hostility"


def test_llm_error_falls_back_without_crashing():
    llm = ScriptedLLM([LLMError("backend down")])
    tag = TagClassifier(llm).classify(make_pack(), "hi")
    assert tag == "neutral"
