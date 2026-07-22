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


def _gated_pack():
    return make_pack(
        tags=[
            {"id": "warmth", "description": "warm", "sentiment": "positive"},
            {
                "id": "reciprocate",
                "description": "accept the romantic advance",
                "sentiment": "positive",
                "unlock_at": 0.6,
                "lock_at": 1.0,
            },
            {"id": "hostility", "description": "hostile", "sentiment": "negative"},
            {"id": "neutral", "description": "nothing", "sentiment": "neutral"},
        ],
        deltas={
            "warmth": {"affection": 5.0, "trust": 3.0, "bond": 0.5},
            "reciprocate": {"affection": 5.0, "trust": 3.0, "bond": 0.5},
            "hostility": {"affection": -6.0, "trust": -4.0, "bond": -0.2},
            "neutral": {"affection": 0.0, "trust": 0.0, "bond": 0.0},
        },
        blocks={"warmth": "", "reciprocate": "", "hostility": "", "neutral": ""},
    )


def test_gated_tag_hidden_below_its_window():
    llm = ScriptedLLM([json.dumps({"tag": "neutral"})])
    TagClassifier(llm).classify(_gated_pack(), "come closer", ratio=0.1)
    enum = llm.formats[0]["properties"]["tag"]["enum"]
    assert "reciprocate" not in enum  # engine won't even offer it early
    assert "warmth" in enum


def test_gated_tag_offered_inside_its_window():
    llm = ScriptedLLM([json.dumps({"tag": "reciprocate"})])
    tag = TagClassifier(llm).classify(_gated_pack(), "come closer", ratio=0.8)
    assert "reciprocate" in llm.formats[0]["properties"]["tag"]["enum"]
    assert tag == "reciprocate"


def test_no_ratio_offers_all_tags():
    llm = ScriptedLLM([json.dumps({"tag": "reciprocate"})])
    TagClassifier(llm).classify(_gated_pack(), "hi")  # no ratio → backward compatible
    assert "reciprocate" in llm.formats[0]["properties"]["tag"]["enum"]


def test_fallback_is_always_offered_even_when_gated_out():
    # A pathological pack where the fallback itself carries a late window: it must
    # still be offered so there's always a valid choice.
    pack = make_pack(
        tags=[
            {"id": "warmth", "description": "w", "sentiment": "positive",
             "unlock_at": 0.9, "lock_at": 1.0},
            {"id": "hostility", "description": "h", "sentiment": "negative"},
            {"id": "neutral", "description": "n", "sentiment": "neutral",
             "unlock_at": 0.9, "lock_at": 1.0},
        ],
    )
    llm = ScriptedLLM([json.dumps({"tag": "neutral"})])
    TagClassifier(llm).classify(pack, "hi", ratio=0.0)
    assert "neutral" in llm.formats[0]["properties"]["tag"]["enum"]  # fallback kept


def test_classifier_context_is_capped_to_recent_turns():
    from engine.perception import _CONTEXT_TURNS
    from engine.prompt_manager import DialogueTurn

    class Capturing:
        def chat(self, messages, *, model=None, fmt=None, options=None):
            self.seen = messages
            return json.dumps({"tag": "warmth"})

    window = tuple(
        DialogueTurn("user" if i % 2 == 0 else "assistant", f"turn{i}") for i in range(40)
    )
    cap = Capturing()
    TagClassifier(cap).classify(make_pack(), "now", window)
    # system prompt + recent window turns + the final user message.
    assert len(cap.seen) - 2 == _CONTEXT_TURNS
    assert cap.seen[-1]["content"] == "now"
    assert cap.seen[1]["content"] == "turn34"  # last _CONTEXT_TURNS of 40
