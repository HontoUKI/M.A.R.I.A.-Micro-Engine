"""Execution facts expire by model turns and survive newer failed retries."""

from engine.action_history import ActionHistory


def test_selected_ammunition_has_current_stock_and_single_copy_of_measured_changes():
    notes = ActionHistory()
    notes.begin_turn()
    notes.observe(
        feed(
            action(
                "shots",
                actor="reflex",
                routine="spell_fighting",
                changes=[
                    {"item": "minecraft:spectral_arrow", "change": -10, "reason": "guard_reflex"},
                    {"item": "bread", "change": -1, "reason": "healing_reflex"},
                ],
            )
        )
    )
    text = notes.render([{"item": "spectral_arrow", "remaining": 0}])
    assert text.startswith("Ammunition")
    assert "spectral_arrow: remaining 0" in text
    assert text.count("-10") == 1
    assert "reason: guard_reflex; actor: reflex" in text
    assert "-1 bread, reason: healing_reflex" in text
    for _ in range(5):
        notes.begin_turn()
    text = notes.render([{"item": "spectral_arrow", "remaining": 0}])
    assert "remaining 0" in text and "-10" not in text
    assert "Ammunition" not in notes.render()


def feed(*rows, stream="world"):
    return {"stream": stream, "records": list(rows)}


def action(key="placed", **fields):
    return {
        "id": key,
        "sequence": 1,
        "revision": 1,
        "actor": "agent",
        "goal": {"verb": "place", "object": "crafting_table"},
        "outcome": "reached",
        "changes": [{"item": "crafting_table", "change": -1, "reason": "placed"}],
        **fields,
    }


def test_five_turns_no_poll_refresh_and_no_resurrection():
    notes = ActionHistory()
    for turn in range(1, 8):
        notes.begin_turn()
        notes.observe(feed(action()))
        assert ("#placed" in notes.render()) is (turn <= 5)
        notes.observe(feed(action()))
        assert ("#placed" in notes.render()) is (turn <= 5)


def test_new_failed_retry_does_not_overwrite_success_and_context():
    notes = ActionHistory()
    notes.begin_turn()
    notes.observe(feed(action(parent="plan-one")))
    notes.begin_turn()
    notes.observe(
        feed(
            action(), action("retry", sequence=2, outcome="foreclosed", why="no planks", changes=[])
        )
    )
    text = notes.render()
    assert "#placed" in text and "#retry" in text and "no planks" in text
    assert "-1 crafting_table, reason: placed" in text
    assert "parent: plan-one" in text
    assert "<play>" not in text


def test_revision_updates_are_new_facts_and_world_change_clears_history():
    notes = ActionHistory()
    for _ in range(5):
        notes.begin_turn()
        notes.observe(feed(action()))
    notes.begin_turn()
    notes.observe(feed(action(revision=2, outcome="foreclosed")))
    assert "foreclosed" in notes.render()
    notes.observe(feed(stream="other"))
    assert not notes.cells


def test_already_true_is_not_reported_as_work_performed():
    notes = ActionHistory()
    notes.begin_turn()
    notes.observe(feed(action(already=True, changes=[])))
    assert "already true — nothing done" in notes.render()
    assert "-1 crafting_table" not in notes.render()


def test_service_retains_history_across_request_runtimes_and_reset(tmp_path):
    from app.contracts import ChatMessage
    from app.service import EngineService
    from engine.registry import PackRegistry
    from tests._packs import make_pack

    class Hands:
        def history(self):
            return []

        def sight(self):
            return {"actions": feed(action())}

        def offer(self):
            return {"game": "Test", "glossary": True, "affordances": [{"verb": "place"}]}

    class Model:
        def __init__(self):
            self.inputs = []

        def chat(self, messages, *, fmt=None, **kwargs):
            if fmt:
                return '{"tag":"neutral"}'
            self.inputs.append(str(messages))
            return "Waiting."

    model = Model()
    service = EngineService(
        registry=PackRegistry({"aria": make_pack()}),
        llm=model,
        hands=Hands(),
        sessions_dir=str(tmp_path / "s"),
        scenes_dir=str(tmp_path / "c"),
    )
    for turn in range(1, 7):
        service.complete("aria", [ChatMessage(role="user", content="Wait")], session_key="one")
        assert ("#placed" in model.inputs[-1]) is (turn <= 5)
    service.reset_relationship("aria", "one")
    assert not service.action_histories
