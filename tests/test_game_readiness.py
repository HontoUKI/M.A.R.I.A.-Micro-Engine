"""Readiness is next-turn feedback, not a refusal of valid Router source."""
from __future__ import annotations

import json
from copy import deepcopy

import pytest

from app.contracts import ChatMessage
from app.service import EngineService
from engine.character import CharacterRuntime
from engine.hands import Goal, Intention, read_intention
from engine.prompt_manager import PromptManager
from engine.registry import PackRegistry
from tests._packs import make_pack

PARENT_SOURCE = '@teach(details: "forward") def parent() { run(child) }'
CHILD_SOURCE = '@teach(details: "pause") def child() { wait(seconds: 0.1) }'
PARENT_GOAL = {
    "verb": "teach", "object": "parent",
    "where": {"routine": {"steps": [{"call": "child"}], "params": {}}},
}
CHILD_GOAL = {
    "verb": "teach", "object": "child",
    "where": {"routine": {"steps": [{"verb": "wait", "where": {"seconds": 0.1}}]}},
}
UNRESOLVED = {
    "name": "child", "step_path": "steps[0].where.routine.steps[0]",
    "reason": "missing_routine",
}


@pytest.mark.parametrize("reason,name", [
    ("missing_routine", "child"), ("requires_binding", "$routine"),
])
def test_readiness_keeps_source_steps_and_does_not_become_unread(reason, name):
    call = {**UNRESOLVED, "name": name, "reason": reason}
    response = {"steps": [PARENT_GOAL], "repeat": 2, "ready": False,
                "unresolved_calls": [call]}
    intention, speech = read_intention("Saved.<play>" + PARENT_SOURCE + "</play>",
                                      lambda source: response)
    assert speech == "Saved."
    assert intention and intention.repeat == 2 and intention.unread == ()
    assert intention.steps == (Goal("teach", {k: v for k, v in PARENT_GOAL.items()
                                             if k != "verb"}),)
    assert tuple(map(json.loads, intention.readiness)) == (call,)
    assert not Intention(readiness=intention.readiness), "a diagnostic alone is not an action"
    assert response["steps"] == [PARENT_GOAL], "the consumer must not mutate compiled source"


@pytest.mark.parametrize("metadata", [{}, {"ready": True, "unresolved_calls": []}])
def test_older_reader_and_ready_reader_keep_the_same_execution(metadata):
    response = {"steps": [{"verb": "wait"}], **metadata}
    intention, speech = read_intention("Okay.<play>wait()</play>", lambda source: response)
    assert speech == "Okay." and intention.steps == (Goal("wait"),)
    assert not intention.unread and not intention.readiness


class ForwardPort:
    """Canned Router wire records; no game vocabulary is parsed by the consumer."""

    def __init__(self):
        self.known = set()
        self.reads = []
        self.submissions = []
        self.records = []

    def history(self):
        return self.records

    def sight(self):
        # Feedback must survive a world overview larger than the model budget.
        return {"large_world": "terrain " * 6000}

    def offer(self):
        return {"game": "Test", "affordances": [{"verb": "teach"}, {"verb": "run"}]}

    def read(self, text):
        self.reads.append(text)
        goals = {PARENT_SOURCE: [PARENT_GOAL], CHILD_SOURCE: [CHILD_GOAL],
                 "run(parent)": [{"verb": "run", "object": "parent"}]}[text]
        unresolved = [UNRESOLVED] if text == PARENT_SOURCE and "child" not in self.known else []
        return {"steps": deepcopy(goals), "repeat": 1, "word": None,
                "ready": not unresolved, "unresolved_calls": deepcopy(unresolved)}

    def act(self, intention):
        self.submissions.append(intention)
        goal, = intention.steps
        if goal.verb == "teach":
            name = goal.fields["object"]
            self.known.add(name)
            record = {"outcome": "routine_saved", "saved": True, "name": name, "version": 1}
            self.records.append(record)
            return record
        return {"id": "running-parent", "open": True}


def test_forward_declaration_is_saved_then_readiness_is_checked_again():
    port = ForwardPort()
    runtime = CharacterRuntime(make_pack(), object(), hands=port)
    speech, did = runtime._reach_for_the_game("Saving.<play>" + PARENT_SOURCE + "</play>")
    assert speech == "Saving." and did and "parent" in port.known
    assert port.records == [
        {"outcome": "routine_saved", "saved": True, "name": "parent", "version": 1}
    ]
    assert not runtime._unread
    block = runtime._game_block()
    assert "ready: false" in block and UNRESOLVED["step_path"] in block
    assert "missing_routine" in block and "routine_saved/saved: true" in block
    notice = block.split("\n\n", 1)[0]
    assert "could not be read" not in notice and "nothing moved" not in notice
    assert "ready: false" not in runtime._game_block(), "readiness is said once"
    runtime._reach_for_the_game("<play>" + CHILD_SOURCE + "</play>")
    reread, _ = read_intention("<play>" + PARENT_SOURCE + "</play>", port.read)
    assert reread and not reread.readiness and not reread.unread
    _, did = runtime._reach_for_the_game("<play>run(parent)</play>")
    assert did and port.submissions[-1].steps == (Goal("run", {"object": "parent"}),)


def test_binding_warning_does_not_block_any_returned_step():
    port = ForwardPort()
    dynamic = {"name": "$routine", "step_path": "steps[1]", "reason": "requires_binding"}
    response = {"steps": [CHILD_GOAL, {"verb": "wait"}], "ready": False,
                "unresolved_calls": [dynamic]}
    port.read = lambda text: response
    submitted = []
    port.act = lambda intention: submitted.append(intention) or {"open": True}
    runtime = CharacterRuntime(make_pack(), object(), hands=port)
    _, did = runtime._reach_for_the_game("<play>opaque source</play>")
    assert did and [goal.as_wire() for goal in submitted[0].steps] == response["steps"]
    block = runtime._game_block()
    assert "requires_binding" in block and '"step_path": "steps[1]"' in block
    assert "nothing moved" not in block.split("\n\n", 1)[0]


def test_readiness_survives_service_recreation_failure_and_budget_then_clears(tmp_path):
    class Model:
        def __init__(self):
            self.inputs = []
            self.fail = False
            self.replies = iter([PARENT_SOURCE, "", CHILD_SOURCE, "run(parent)", ""])

        def chat(self, messages, *, fmt=None, **kwargs):
            if fmt:
                return '{"tag":"neutral"}'
            if self.fail:
                raise RuntimeError("model unavailable")
            self.inputs.append(messages)
            return "Okay.<play>" + next(self.replies) + "</play>"

    port, model = ForwardPort(), Model()
    service = EngineService(
        registry=PackRegistry({"aria": make_pack()}), llm=model, hands=port,
        sessions_dir=str(tmp_path / "sessions"), scenes_dir=str(tmp_path / "scenes"),
        prompt_manager=PromptManager(max_tokens=1800),
    )
    messages = [ChatMessage(role="user", content="Go")]
    first = service.complete("aria", messages, session_key="alice")
    assert first.did and first.game_feedback_pending
    assert set(service.game_feedback[("alice", "aria")]) == {"_game_readiness"}
    assert "parent" in port.known
    service.complete("aria", messages, session_key="bob")
    assert "ready: false" not in str(model.inputs[-1])
    model.fail = True
    with pytest.raises(RuntimeError, match="model unavailable"):
        service.complete("aria", messages, session_key="alice")
    assert ("alice", "aria") in service.game_feedback
    model.fail = False
    second = service.complete("aria", messages, session_key="alice")
    text = str(model.inputs[-1])
    assert "ready: false" in text and UNRESOLVED["step_path"] in text
    assert "World details omitted" in text
    assert "nothing moved" not in text and second.did and not second.game_feedback_pending
    assert port.known == {"parent", "child"}
    assert ("alice", "aria") not in service.game_feedback
    third = service.complete("aria", messages, session_key="alice")
    assert third.did and not third.game_feedback_pending
    assert "ready: false" not in str(model.inputs[-1])
    service.complete("aria", messages, session_key="alice")
    assert "ready: false" not in str(model.inputs[-1])
    service.game_feedback[("alice", "aria")] = {"_game_readiness": ("old diagnostic",)}
    service.reset_relationship("aria", "alice")
    assert ("alice", "aria") not in service.game_feedback
