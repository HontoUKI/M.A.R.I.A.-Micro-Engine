"""Character runtime contracts: the full classify → move → voice → remember turn."""
from __future__ import annotations

import json

from engine.character import CharacterRuntime
from engine.memory import VectorStore
from engine.prompt_manager import DialogueTurn
from tests._packs import make_pack


class FakeLLM:
    """Classifier calls carry a `fmt`; voice calls do not — distinguish on that."""

    def __init__(self, *, tag="warmth", reply="Hello there.", embedding=None):
        self.tag = tag
        self.reply = reply
        self.embedding = embedding or [1.0, 0.0, 0.0]
        self.chat_calls = []
        self.embed_calls = []

    def chat(self, messages, *, model=None, fmt=None, options=None):
        self.chat_calls.append({"messages": messages, "fmt": fmt})
        if fmt is not None:
            return json.dumps({"tag": self.tag})
        return self.reply

    def embed(self, text, *, model=None):
        self.embed_calls.append(text)
        return list(self.embedding)


# ---------------------------------------------------------------- basic turn


def test_respond_returns_reply_tag_and_moved_axes():
    llm = FakeLLM(tag="warmth", reply="So kind of you.")
    rt = CharacterRuntime(make_pack(), llm)
    result = rt.respond("you're wonderful")
    assert result.reply == "So kind of you."
    assert result.tag == "warmth"
    # warmth delta: +5 / +3 / +0.5 over 20 / 10 / 0 baseline.
    assert result.axes.affection == 25
    assert result.axes.trust == 13
    assert result.axes.bond == 0.5


def test_turn_makes_exactly_two_chat_calls_classify_then_voice():
    llm = FakeLLM()
    CharacterRuntime(make_pack(), llm).respond("hi")
    assert len(llm.chat_calls) == 2
    assert llm.chat_calls[0]["fmt"] is not None  # classify (constrained)
    assert llm.chat_calls[1]["fmt"] is None  # voice


def test_voice_prompt_carries_steering_block_in_the_tail():
    llm = FakeLLM(tag="hostility")
    CharacterRuntime(make_pack(), llm).respond("you're useless")
    voice_messages = llm.chat_calls[1]["messages"]
    tail = voice_messages[-1]["content"]
    assert "Stay guarded." in tail
    assert "you're useless" in tail


def test_identity_is_pinned_in_system_prefix():
    llm = FakeLLM()
    CharacterRuntime(make_pack(), llm).respond("hi")
    system = llm.chat_calls[1]["messages"][0]
    assert system["role"] == "system"
    assert "Aria" in system["content"]


def test_dialogue_window_is_passed_through_to_voice():
    llm = FakeLLM()
    window = (DialogueTurn("user", "earlier"), DialogueTurn("assistant", "reply"))
    CharacterRuntime(make_pack(), llm).respond("now", dialogue_window=window)
    contents = [m["content"] for m in llm.chat_calls[1]["messages"]]
    assert "earlier" in contents


# ---------------------------------------------------------------- fallback


def test_invalid_classification_uses_fallback_tag():
    llm = FakeLLM(tag="does_not_exist")
    result = CharacterRuntime(make_pack(), llm).respond("hi")
    assert result.tag == "neutral"  # fallback; axes unmoved by neutral delta
    assert result.axes.affection == 20


# ---------------------------------------------------------------- stages


def test_runtime_reports_stage_and_injects_stage_block():
    # make_pack starts at 20/10 → ratio 0.15 → reserved.
    pack = make_pack(stages={"reserved": "You are still guarded.", "very_close": "Warm."})
    llm = FakeLLM(tag="neutral")
    result = CharacterRuntime(pack, llm).respond("hi")
    assert result.stage == "reserved"
    tail = llm.chat_calls[1]["messages"][-1]["content"]
    assert "You are still guarded." in tail


def test_stage_changed_true_when_a_turn_crosses_a_threshold():
    # Start at ratio 0.44 (cautious); a warmth turn (+5 / +3) lifts it to 0.48
    # (comfort), crossing the boundary.
    axes = {
        "affection": {"min": 0, "max": 100, "start": 44},
        "trust": {"min": 0, "max": 100, "start": 44},
        "bond": {"min": 0, "max": 100, "start": 0},
    }
    pack = make_pack(axes=axes, stages={"cautious": "guarded", "comfort": "warmer"})
    result = CharacterRuntime(pack, FakeLLM(tag="warmth")).respond("you're kind")
    assert result.stage == "comfort"
    assert result.stage_changed is True


def test_stage_changed_false_when_no_threshold_crossed():
    runtime = CharacterRuntime(make_pack(stages={"reserved": "r"}), FakeLLM(tag="neutral"))
    result = runtime.respond("hi")
    assert result.stage == "reserved"
    assert result.stage_changed is False


# ---------------------------------------------------------------- idle / decay


def test_idle_decays_axes_toward_baseline():
    llm = FakeLLM(tag="warmth")
    rt = CharacterRuntime(make_pack(), llm)
    rt.respond("you're great")  # affection 20 → 25
    rt.idle()  # decay affection by 2 → 23
    assert rt.state.axes.affection == 23


# ---------------------------------------------------------------- sprites


def test_sprite_resolves_by_tag_then_default():
    pack = make_pack(sprites={"default": "idle.png", "warmth": "happy.png"})
    llm = FakeLLM(tag="warmth")
    assert CharacterRuntime(pack, llm).respond("hi").sprite == "happy.png"


def test_sprite_falls_back_to_default_when_tag_has_none():
    pack = make_pack(sprites={"default": "idle.png"})
    llm = FakeLLM(tag="hostility")
    assert CharacterRuntime(pack, llm).respond("go away").sprite == "idle.png"


def test_no_sprites_yields_none():
    llm = FakeLLM()
    assert CharacterRuntime(make_pack(), llm).respond("hi").sprite is None


# ---------------------------------------------------------------- memory


def test_memory_recall_feeds_the_voice_prompt(tmp_path):
    store = VectorStore(str(tmp_path / "mem"))
    store.add("we talked about the sea", [1.0, 0.0, 0.0], embedding_model="m")
    llm = FakeLLM(embedding=[1.0, 0.0, 0.0])
    rt = CharacterRuntime(make_pack(), llm, memory=store, embed_model="m")
    rt.respond("remember?")
    tail = llm.chat_calls[1]["messages"][-1]["content"]
    assert "we talked about the sea" in tail


def test_memory_stores_the_user_message_after_the_turn(tmp_path):
    store = VectorStore(str(tmp_path / "mem"))
    llm = FakeLLM(embedding=[0.0, 1.0, 0.0])
    rt = CharacterRuntime(make_pack(), llm, memory=store, embed_model="m")
    assert store.count() == 0
    rt.respond("a brand new fact")
    assert store.count() == 1
    # embedded once, reused for both search and store.
    assert len(llm.embed_calls) == 1


def test_recall_searches_before_storing_current_message(tmp_path):
    """The message being answered must not be recalled into its own prompt."""
    store = VectorStore(str(tmp_path / "mem"))
    llm = FakeLLM(embedding=[1.0, 0.0, 0.0])
    rt = CharacterRuntime(make_pack(), llm, memory=store, embed_model="m")
    rt.respond("unique-phrase-xyz")
    tail = llm.chat_calls[1]["messages"][-1]["content"]
    # It appears as the user message, but not inside a [Recalled] section.
    assert "[Recalled]" not in tail
