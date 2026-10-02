"""Failed delivery and unread actions must reach the next real game turn."""
from types import SimpleNamespace

import pytest

from engine.character import CharacterRuntime
from engine.glossary import GlossaryNotes
from engine.hands import read_intention
from tests._packs import make_pack


class Hands:
    def history(self):
        return []

    def sight(self):
        return {}

    def offer(self):
        return {"game": "Test", "affordances": [{"verb": "move"}]}

    def read(self, text):
        return {"steps": [{"verb": "move"}]}

    def act(self, intention):
        return {}


@pytest.mark.parametrize("phase", ["read", "act"])
def test_delivery_failure_is_reported_once_after_reconnect_without_claiming_outcome(phase):
    hands = Hands()
    calls = []

    def failed(*args):
        calls.append(phase)
        raise ConnectionError("response lost")

    setattr(hands, phase, failed)
    runtime = object.__new__(CharacterRuntime)
    runtime._hands = hands
    runtime._glossary = GlossaryNotes()
    runtime._pack = make_pack()
    runtime._state = SimpleNamespace(axes={})
    runtime._paused = None
    runtime._within_bounds = lambda intention: (intention, ())
    speech, did = runtime._reach_for_the_game("Okay.<play>move()</play>")
    assert speech == "Okay." and did == () and calls == [phase]
    delivery = runtime._game_delivery_issue
    block = runtime._game_block()
    assert "connection failure" in block
    if phase == "read":
        assert "not sent for execution" in block
    else:
        assert "may have been accepted" in block
        assert "nothing moved" not in delivery
    assert "connection failure" not in runtime._game_block()


def test_empty_block_produces_feedback_but_speech_only_is_a_valid_wait():
    assert read_intention("Wait.<play> </play>", Hands().read)[0].unread
    assert not read_intention("Wait.", Hands().read)[0].unread
    assert not read_intention("Wait.<play></play>")[0].unread


def test_runtime_marks_unread_calls_for_game_loop_and_clears_feedback_on_next_turn():
    class Model:
        def __init__(self):
            self.voices = []

        def chat(self, messages, *, fmt=None, **kwargs):
            if fmt:
                return '{"tag":"neutral"}'
            self.voices.append(messages)
            return "Waiting.<play></play>" if len(self.voices) == 1 else "I will wait."

    model = Model()
    runtime = CharacterRuntime(make_pack(), model, hands=Hands())
    assert runtime.respond("Go").game_feedback_pending
    assert not runtime.respond("[waiting]").game_feedback_pending
    assert "contained no action calls" in str(model.voices[-1])


def test_play_delivers_local_feedback_through_normal_pause_without_router_events(monkeypatch):
    from tools import play

    clock = {"now": 100.0}
    calls = []

    def complete(*args, **kwargs):
        calls.append(kwargs)
        return SimpleNamespace(reply="", did=(), game_feedback_pending=len(calls) < 3)

    service = SimpleNamespace(hands=None, has_model=lambda name: True,
                              registry=SimpleNamespace(get=lambda name: SimpleNamespace(
                                  meta=SimpleNamespace(display_name="Test"), unseen_notes=())),
                              complete=complete)

    def events(*args):
        for now, event in [(100, {"kind": "heard", "who": "Tester", "said": "Go"}),
                           (144, None), (145, None), (164, None), (165, None), (200, None)]:
            clock["now"] = now
            yield event

    monkeypatch.setattr(play, "get_service", lambda: service)
    monkeypatch.setattr(play, "_her_name", lambda port: "Test")
    monkeypatch.setattr(play, "_world_id", lambda port: "isolated")
    monkeypatch.setattr(play, "_listen", lambda port: ())
    monkeypatch.setattr(play, "_ticking", events)
    monkeypatch.setattr(play.time, "time", lambda: clock["now"])
    monkeypatch.setattr(play.sys, "argv", ["play", "--character", "test", "--port", "http://test/v0"])
    assert play.main() == 0
    assert len(calls) == 3


@pytest.mark.parametrize("failure", ["unread", "read_connection", "act_connection"])
def test_feedback_crosses_service_requests_isolated_by_session_and_survives_world_budget(
    tmp_path, failure
):
    from app.contracts import ChatMessage
    from app.service import EngineService
    from engine.prompt_manager import PromptManager
    from engine.registry import PackRegistry

    class Port(Hands):
        failed = False

        def sight(self):
            return {"large_world": "terrain " * 6000}

        def read(self, text):
            if failure == "unread":
                return {"error": "test syntax needs parentheses"}
            if failure == "read_connection":
                raise ConnectionError("read failed")
            return super().read(text)

        def act(self, intention):
            raise ConnectionError("response lost after submission")

    class Model:
        def __init__(self):
            self.inputs = []
            self.fail = False

        def chat(self, messages, *, fmt=None, **kwargs):
            if fmt:
                return '{"tag":"neutral"}'
            if self.fail:
                raise RuntimeError("model unavailable")
            self.inputs.append(messages)
            return "<play>move()</play>" if len(self.inputs) == 1 else "I will wait."

    pack, model = make_pack(), Model()
    service = EngineService(
        registry=PackRegistry({"aria": pack}), llm=model, hands=Port(),
        sessions_dir=str(tmp_path / "sessions"), scenes_dir=str(tmp_path / "scenes"),
        prompt_manager=PromptManager(max_tokens=1800),
    )
    messages = [ChatMessage(role="user", content="Go")]
    assert service.complete("aria", messages, session_key="alice").game_feedback_pending
    service.complete("aria", messages, session_key="bob")
    assert "test syntax" not in str(model.inputs[-1])
    assert "connection failure" not in str(model.inputs[-1])
    model.fail = True
    with pytest.raises(RuntimeError, match="model unavailable"):
        service.complete("aria", messages, session_key="alice")
    assert ("alice", "aria") in service.game_feedback
    model.fail = False
    result = service.complete("aria", messages, session_key="alice")
    text = str(model.inputs[-1])
    expected = "test syntax" if failure == "unread" else "connection failure"
    assert expected in text, "the service builds a new runtime for every request"
    assert "World details omitted" in text
    assert not result.game_feedback_pending
    service.complete("aria", messages, session_key="alice")
    assert expected not in str(model.inputs[-1])
    service.game_feedback[("alice", "aria")] = {"_unread": ("old error",)}
    service.reset_relationship("aria", "alice")
    assert ("alice", "aria") not in service.game_feedback
