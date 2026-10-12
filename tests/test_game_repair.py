"""A rejected draft stays private and available for one bounded repair turn."""
from hashlib import sha256

import pytest

from app.contracts import ChatMessage
from app.service import EngineService
from engine.character import CharacterRuntime
from engine.game_repair import REPAIR_CONTEXT_LIMIT, FailedSource
from engine.hands import read_intention
from engine.prompt_manager import PromptManager
from engine.registry import PackRegistry
from tests._packs import make_pack
from tests.test_game_feedback import Hands


def test_reader_refusal_retains_the_exact_draft_revision_and_error_fragment():
    source = '@teach(details: "draft") def probe() {\n wait(seconds: bread)\n}'
    intention, speech = read_intention(
        f"Waiting.<play>{source}</play>",
        lambda text: {"error": "seconds needs number", "code": "invalid_argument",
                      "line": 2, "column": 2, "source_line": " wait(seconds: bread)"},
    )
    assert speech == "Waiting." and not intention
    failed = getattr(intention, "failed_source", None)
    assert failed is not None, "the reader error currently discards the source needed to repair it"
    assert failed.revision == sha256(source.encode()).hexdigest()
    assert failed.source == source and failed.source_complete
    assert "wait(seconds: bread)" in failed.fragment
    assert failed.diagnostic["code"] == "invalid_argument"


def test_long_rejected_source_retains_a_local_fragment_without_claiming_completeness():
    source = 'prefix\\"\x00\n' * 2000 + 'the-error-near-the-end'
    failed = FailedSource.capture(source, {
        "error": '\x00\\"' * 2000, "why": '\x00\\"' * 2000,
        "code": 'x' * 1000, "expected": 'y' * 1000,
        "offset": len(source) - 20, "private_packet": "never-project-this",
    })
    assert not failed.source_complete and failed.source_chars == len(source)
    assert failed.revision == sha256(source.encode()).hexdigest()
    assert 'the-error-near-the-end' in failed.fragment
    assert len(failed.render()) <= REPAIR_CONTEXT_LIMIT
    assert 'never-project-this' not in failed.render()
    with pytest.raises(TypeError):
        failed.diagnostic["error"] = "changed"


def test_saved_false_authoring_retains_source_and_reason_but_does_not_report_execution():
    hands = Hands()
    hands.read = lambda text: {"steps": [{"verb": "teach", "object": "probe"}]}
    hands.act = lambda intention: {"error": "routine_rejected", "saved": False,
                                  "why": "depends on mods; cannot be permanent"}
    runtime = CharacterRuntime(make_pack(), object(), hands=hands)
    source = '@teach(scope: permanent) def probe() { run(modchild) }'
    speech, did = runtime._reach_for_the_game(f"Okay.<play>{source}</play>")
    assert speech == "Okay." and did == ()
    assert runtime._game_repair.source == source
    assert runtime._game_repair.stage == "save_refusal"
    assert "depends on mods" in runtime._game_repair.render()
    assert "not saved" in runtime._game_repair.render()
    assert "Nothing was executed" not in runtime._game_repair.render()


def test_uncertain_authoring_delivery_is_not_a_confirmed_draft_refusal():
    hands = Hands()
    hands.read = lambda text: {"steps": [{"verb": "teach"}]}
    def lost(intention):
        raise ConnectionError("response lost")
    hands.act = lost
    runtime = CharacterRuntime(make_pack(), object(), hands=hands)
    _, did = runtime._reach_for_the_game("<play>opaque draft</play>")
    assert did == () and runtime._game_repair is None
    assert "connection failure" in runtime._game_block()


def test_repair_survives_request_recreation_failure_and_world_budget_then_clears(tmp_path):
    source = 'draft-repair-private-marker\ninvalid draft'
    class Port(Hands):
        def __init__(self):
            self.submissions = []
        def sight(self):
            return {"large_world": "terrain " * 6000}
        def read(self, text):
            return {"error": "bad argument", "code": "invalid_argument", "line": 2}
        def act(self, intention):
            self.submissions.append(intention)

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
            return "Okay."

    port, model = Port(), Model()
    service = EngineService(
        registry=PackRegistry({"aria": make_pack()}), llm=model, hands=port,
        sessions_dir=str(tmp_path / "sessions"), scenes_dir=str(tmp_path / "scenes"),
        prompt_manager=PromptManager(max_tokens=1800),
    )
    runtime = CharacterRuntime(make_pack(), object(), hands=port)
    speech, did = runtime._reach_for_the_game(f"Waiting.<play>{source}</play>")
    assert speech == "Waiting." and did == () and not port.submissions
    service.game_feedback[("alice", "aria")] = {
        "_game_repair": runtime._game_repair, "_unread": runtime._unread,
    }
    messages = [ChatMessage(role="user", content="Continue")]
    service.complete("aria", messages, session_key="bob")
    assert source.splitlines()[0] not in str(model.inputs[-1])
    model.fail = True
    with pytest.raises(RuntimeError, match="model unavailable"):
        service.complete("aria", messages, session_key="alice")
    assert service.game_feedback[("alice", "aria")]["_game_repair"] is runtime._game_repair
    model.fail = False
    result = service.complete("aria", messages, session_key="alice")
    text = str(model.inputs[-1])
    assert source.splitlines()[0] in text and "World details omitted" in text
    assert result.reply == "Okay." and not result.did and not result.game_feedback_pending
    assert ("alice", "aria") not in service.game_feedback
    service.complete("aria", messages, session_key="alice")
    assert source.splitlines()[0] not in str(model.inputs[-1])
    for file in (tmp_path / "sessions").rglob("*"):
        if file.is_file():
            assert source.splitlines()[0] not in file.read_text(encoding="utf-8")
    service.game_feedback[("alice", "aria")] = {"_game_repair": runtime._game_repair}
    service.reset_relationship("aria", "alice")
    assert ("alice", "aria") not in service.game_feedback
