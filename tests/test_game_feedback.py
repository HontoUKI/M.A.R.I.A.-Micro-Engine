"""Failed delivery and unread actions must reach the next real game turn."""
from types import SimpleNamespace

import pytest

from engine.character import CharacterRuntime
from engine.glossary import GlossaryNotes
from engine.hands import GamePort, GameRequestRejected, Goal, read_intention
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


@pytest.mark.parametrize("method", ["act", "resume", "resume_plan", "abandon", "abandon_plan"])
def test_explicit_router_refusal_reaches_next_turn_without_a_success_claim(method):
    hands = Hands()
    refusal = {"error": "invalid bound parameters", "code": "invalid_argument", "saved": False}
    setattr(hands, method, lambda *args: refusal)
    runtime = CharacterRuntime(make_pack(), object(), hands=hands)
    source = "move()"
    if method in {"resume", "abandon"}:
        runtime._paused = "active-attempt"
        source = "continue" if method == "resume" else "drop"
    if method in {"resume_plan", "abandon_plan"}:
        runtime._unfinished = {"plan": "active-plan"}
        source = "continue" if method == "resume_plan" else "drop"
    if method != "act":
        hands.read = lambda text: {"word": source}
    speech, did = runtime._reach_for_the_game(f"Okay.<play>{source}</play>")
    assert speech == "Okay." and did == ()
    block = runtime._game_block()
    assert "confirmed request refusal" in block
    assert "invalid bound parameters" in block and "invalid_argument" in block
    assert "saved" in block
    assert "connection failure" not in block
    assert "confirmed request refusal" not in runtime._game_block()


def test_http_port_preserves_reader_diagnostics_but_rejects_failed_action_requests(monkeypatch):
    import requests

    refusal = {"error": "duplicate_argument", "saved": False}
    class Response:
        status_code = 422

        def json(self):
            return refusal

        def raise_for_status(self):
            raise requests.HTTPError("server failed")

    monkeypatch.setattr("engine.hands.requests.post", lambda *args, **kwargs: Response())
    port = GamePort("http://test/v0")
    assert port.read("<play>move()</play>") == refusal
    with pytest.raises(GameRequestRejected) as rejected:
        port.take(Goal("move"))
    assert rejected.value.result == refusal and rejected.value.status == 422
    Response.status_code = 503
    with pytest.raises(requests.HTTPError):
        port.take(Goal("move"))


def test_refusal_keeps_raw_result_but_prompt_feedback_does_not_repeat_the_whole_catalog():
    result = {
        "error": "verb unavailable", "code": "unknown_verb",
        "affordances": [{"verb": "large_catalog_entry"}] * 1000,
    }
    refusal = GameRequestRejected(result, 422)
    assert refusal.result is result
    assert "unknown_verb" in str(refusal) and "422" in str(refusal)
    assert "large_catalog_entry" not in str(refusal)


@pytest.mark.parametrize("error", ["invalid bound parameters", "effect_unconfirmed"])
def test_immediate_closed_action_is_feedback_even_when_http_request_was_accepted(error):
    hands = Hands()
    hands.act = lambda intention: {
        "id": "closed-action", "open": False, "outcome": "foreclosed",
        "foreclosed_by": error, "confirmation": {"completion_basis": None},
    }
    runtime = CharacterRuntime(make_pack(), object(), hands=hands)
    speech, did = runtime._reach_for_the_game("Okay.<play>move()</play>")
    assert speech == "Okay." and did == ()
    block = runtime._game_block()
    assert "closed action" in block and "foreclosed" in block and error in block
    assert "confirmed request refusal" not in block
    assert "check" in block and "confirmation" in block


@pytest.mark.parametrize("replacement", [False, True])
def test_drop_releases_both_paused_work_and_closed_intention_before_replacement(replacement):
    calls = []
    hands = Hands()
    hands.read = lambda text: {
        "word": "drop", "steps": [{"verb": "move"}] if replacement else []
    }
    hands.abandon = lambda key: calls.append(("attempt", key))
    hands.abandon_plan = lambda key: calls.append(("plan", key))
    hands.act = lambda intention: calls.append(("act", intention.steps[0].verb))
    runtime = CharacterRuntime(make_pack(), object(), hands=hands)
    runtime._paused = "paused"
    runtime._unfinished = {"plan": "closed-plan"}
    speech, did = runtime._reach_for_the_game("Okay.<play>drop</play>")
    assert speech == "Okay."
    assert calls == [("attempt", "paused"), ("plan", "closed-plan")] + (
        [("act", "move")] if replacement else []
    )
    assert did


@pytest.mark.parametrize("plan_outcome", ["abandoned", "foreclosed"])
def test_drop_accepts_the_closed_records_the_router_really_returns(plan_outcome):
    # The Router answers abandon with the record it just closed; a plan keeps the
    # outcome it already had. Stubs returning None hid that a release was being
    # reported as a failed action and stopped the rest of the drop.
    calls = []
    hands = Hands()
    hands.read = lambda text: {"word": "drop", "steps": [{"verb": "move"}]}
    hands.abandon = lambda key: calls.append(("attempt", key)) or {
        "id": key, "open": False, "outcome": "abandoned",
    }
    hands.abandon_plan = lambda key: calls.append(("plan", key)) or {
        "id": key, "outcome": plan_outcome,
    }
    hands.act = lambda intention: calls.append(("act", intention.steps[0].verb)) or {
        "id": "new", "open": True,
    }
    runtime = CharacterRuntime(make_pack(), object(), hands=hands)
    runtime._paused = "paused"
    runtime._unfinished = {"plan": "closed-plan"}
    speech, did = runtime._reach_for_the_game("Okay.<play>drop</play>")
    assert calls == [("attempt", "paused"), ("plan", "closed-plan"), ("act", "move")]
    assert did and "closed action" not in runtime._game_block()


def test_http_abandon_returns_the_closed_record_without_raising(monkeypatch):
    closed = {"id": "a1", "open": False, "outcome": "abandoned"}

    class Response:
        status_code = 200

        def json(self):
            return closed

    monkeypatch.setattr("engine.hands.requests.post", lambda *args, **kwargs: Response())
    port = GamePort("http://test/v0")
    assert port.abandon("a1") == closed
    assert port.abandon_plan("p1") == closed


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


def test_empty_block_and_speech_only_are_valid_waits():
    assert not read_intention("Wait.<play> </play>", Hands().read)[0].unread
    assert not read_intention("Wait.", Hands().read)[0].unread
    assert not read_intention("Wait.<play></play>")[0].unread


def test_ignored_second_lookup_gets_one_turn_of_feedback_then_empty_wait_stops(tmp_path):
    from app.contracts import ChatMessage
    from app.service import EngineService
    from engine.registry import PackRegistry

    class Port(Hands):
        def offer(self):
            return {**super().offer(), "glossary": True}

        def glossary(self, name):
            return {"name": name, "text": "Reference article"}

    class Model:
        def __init__(self):
            self.inputs = []

        def chat(self, messages, *, fmt=None, **kwargs):
            if fmt:
                return '{"tag":"neutral"}'
            self.inputs.append(messages)
            return ["<lookup>Teach</lookup>", "<play><lookup>Other</lookup></play>",
                    "Done.<play></play>"][len(self.inputs) - 1]

    model = Model()
    service = EngineService(registry=PackRegistry({"aria": make_pack()}), llm=model,
                            hands=Port(), sessions_dir=str(tmp_path / "s"),
                            scenes_dir=str(tmp_path / "c"))
    first = service.complete("aria", [ChatMessage(role="user", content="Go")], session_key="one")
    assert first.game_feedback_pending and not first.did
    second = service.complete("aria", [ChatMessage(role="user", content="[waiting]")],
                              session_key="one")
    assert "additional lookup" in str(model.inputs[-1])
    assert second.reply == "Done." and not second.game_feedback_pending and not second.did


def test_runtime_marks_unread_calls_for_game_loop_and_clears_feedback_on_next_turn():
    class Reader(Hands):
        def read(self, text):
            return {"error": "move needs parentheses"}

    class Model:
        def __init__(self):
            self.voices = []

        def chat(self, messages, *, fmt=None, **kwargs):
            if fmt:
                return '{"tag":"neutral"}'
            self.voices.append(messages)
            return "Waiting.<play>move</play>" if len(self.voices) == 1 else "I will wait."

    model = Model()
    runtime = CharacterRuntime(make_pack(), model, hands=Reader())
    assert runtime.respond("Go").game_feedback_pending
    assert not runtime.respond("[waiting]").game_feedback_pending
    assert "move needs parentheses" in str(model.voices[-1])


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


def test_helper_state_reads_peek_so_they_do_not_spend_her_turns(monkeypatch):
    # The Router carries a selected example for three turn reads of /state; the world
    # id and her name are read beside every turn and must not spend those.
    import io
    import json

    import tools.play as play

    seen = []

    def urlopen(url, timeout=None):
        seen.append(url)
        return io.BytesIO(json.dumps({"world": {"id": "w"}, "her": {"name": "Aria"}}).encode())

    monkeypatch.setattr(play.urllib.request, "urlopen", urlopen)
    assert play._world_id("http://r/v0") == "w"
    assert play._her_name("http://r/v0") == "Aria"
    assert seen == ["http://r/v0/state?peek=1"] * 2
