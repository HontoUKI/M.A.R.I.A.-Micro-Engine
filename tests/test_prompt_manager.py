"""Two-segment prompt assembly contracts.

Uses a word-count estimator so budgets are easy to reason about in tests.
"""
from __future__ import annotations

import pytest

from engine.prompt_manager import DialogueTurn, PromptInputs, PromptManager


def _words(text: str) -> int:
    return len(text.split())


def _manager(max_tokens: int = 1000) -> PromptManager:
    return PromptManager(max_tokens=max_tokens, estimate_tokens=_words)


# ---------------------------------------------------------------- structure


def test_first_message_is_system_prefix_with_identity_and_invariants():
    inputs = PromptInputs(
        identity="You are Aria, a calm archivist.",
        invariants="Never break character.",
        user_message="hello",
    )
    messages = _manager().build_messages(inputs)
    assert messages[0]["role"] == "system"
    assert "Aria" in messages[0]["content"]
    assert "Never break character." in messages[0]["content"]


def test_last_message_is_user_tail_carrying_steering_and_message():
    inputs = PromptInputs(
        identity="You are Aria.",
        steering_block="Lean into shared history.",
        user_message="what did we talk about?",
    )
    messages = _manager().build_messages(inputs)
    last = messages[-1]
    assert last["role"] == "user"
    assert "Lean into shared history." in last["content"]
    assert "what did we talk about?" in last["content"]
    # The user's own words come last, after the private direction.
    assert last["content"].rstrip().endswith("what did we talk about?")


def test_steering_is_not_written_into_system_prefix():
    """The dynamic tail must not leak into the pinned prefix."""
    inputs = PromptInputs(
        identity="You are Aria.",
        steering_block="STEER-XYZ",
        user_message="hi",
    )
    messages = _manager().build_messages(inputs)
    assert "STEER-XYZ" not in messages[0]["content"]


def test_dialogue_window_sits_between_prefix_and_tail_in_order():
    window = (
        DialogueTurn("user", "first"),
        DialogueTurn("assistant", "second"),
        DialogueTurn("user", "third"),
    )
    inputs = PromptInputs(
        identity="You are Aria.",
        user_message="now",
        dialogue_window=window,
    )
    messages = _manager().build_messages(inputs)
    assert messages[0]["role"] == "system"
    assert [m["content"] for m in messages[1:-1]] == ["first", "second", "third"]
    assert messages[-1]["role"] == "user"
    assert "now" in messages[-1]["content"]


# ---------------------------------------------------------------- direction


def test_stage_and_steering_go_into_a_private_direction_note():
    inputs = PromptInputs(
        identity="You are Aria.",
        stage_block="You have grown close to them.",
        steering_block="Be playful.",
        user_message="hi",
    )
    tail = _manager().build_messages(inputs)[-1]["content"]
    # Both blocks appear, wrapped as explicitly private, non-user direction.
    assert "You have grown close to them." in tail
    assert "Be playful." in tail
    assert "not from the user" in tail
    # Stage (climate) precedes steering (weather); the user message is last.
    assert tail.index("close to them") < tail.index("Be playful.") < tail.index("hi")


def test_no_direction_note_without_stage_or_steering():
    inputs = PromptInputs(identity="You are Aria.", user_message="hi")
    tail = _manager().build_messages(inputs)[-1]["content"]
    assert "Private notes" not in tail
    assert tail.strip() == "hi"


# ---------------------------------------------------------------- budget


def test_memory_recall_dropped_before_dialogue_when_budget_tight():
    window = (DialogueTurn("user", "kept turn"),)
    inputs = PromptInputs(
        identity="id",
        user_message="msg",
        memory_recall="a b c d e f g h i j",  # 10 words
        dialogue_window=window,
    )
    # Budget large enough for prefix+tail+one turn, but not for memory.
    messages = _manager(max_tokens=11).build_messages(inputs)
    tail = messages[-1]["content"]
    assert "a b c d" not in tail  # memory dropped
    assert any(m["content"] == "kept turn" for m in messages)  # turn kept


def test_oldest_dialogue_turns_dropped_first():
    # Длиннее пола: ниже него ронять нечего, и утверждение было бы о полу, а не о
    # порядке.
    window = (
        DialogueTurn("user", "oldest oldest oldest"),
        DialogueTurn("assistant", "old"),
        DialogueTurn("user", "newer"),
        DialogueTurn("assistant", "newer still"),
        DialogueTurn("user", "newest"),
    )
    inputs = PromptInputs(
        identity="id",
        user_message="msg",
        dialogue_window=window,
    )
    messages = _manager(max_tokens=5).build_messages(inputs)
    kept = [m["content"] for m in messages[1:-1]]
    assert "oldest oldest oldest" not in kept
    assert "newest" in kept


def test_user_message_is_always_kept_even_over_budget():
    inputs = PromptInputs(
        identity="a very long identity block here",
        user_message="critical question",
        dialogue_window=(DialogueTurn("user", "junk junk junk"),),
    )
    messages = _manager(max_tokens=1).build_messages(inputs)
    assert "critical question" in messages[-1]["content"]


def test_the_newest_turns_survive_a_budget_that_has_nothing_left():
    """Ходы, ради которых поле и заведено.

    09.09 в игре блок мира занял почти весь потолок, бюджет окна вышел
    отрицательным, и окно исчезало ЦЕЛИКОМ: тридцать ходов прошли как тридцать
    первых, и она четырежды слово в слово повторила один и тот же ответ, имея
    предыдущую копию в окне, которого никто не передал. Уронить старые ходы —
    сделка; уронить все — другой персонаж.
    """
    window = (
        DialogueTurn("user", "oldest oldest oldest"),
        DialogueTurn("assistant", "older older older"),
        DialogueTurn("user", "are you listening"),
        DialogueTurn("assistant", "you are listening"),
    )
    inputs = PromptInputs(
        identity="a very long identity block here",
        game_block="a world block that eats the whole ceiling by itself",
        user_message="critical question",
        dialogue_window=window,
    )
    manager = PromptManager(max_tokens=1, estimate_tokens=_words, keep_last=4)
    kept = [m["content"] for m in manager.build_messages(inputs)[1:-1]]
    assert kept == [t.content for t in window]
    assert "critical question" in manager.build_messages(inputs)[-1]["content"]


def test_the_floor_is_the_newest_ones_and_no_more():
    """Пол — не «держать всё»: старое по-прежнему уходит первым."""
    window = tuple(
        DialogueTurn("user" if i % 2 == 0 else "assistant", f"turn{i}") for i in range(8)
    )
    manager = PromptManager(max_tokens=1, estimate_tokens=_words, keep_last=4)
    kept = [
        m["content"]
        for m in manager.build_messages(
            PromptInputs(identity="id", user_message="msg", dialogue_window=window)
        )[1:-1]
    ]
    assert kept == ["turn4", "turn5", "turn6", "turn7"]


def test_a_prompt_over_its_ceiling_says_so(caplog):
    """Молчаливый перерасход — это и есть дефект: платит за него её память."""
    import logging

    inputs = PromptInputs(
        identity="a very long identity block here",
        game_block="a world block that eats the whole ceiling by itself",
        user_message="critical question",
        dialogue_window=(DialogueTurn("user", "junk junk junk"),),
    )
    with caplog.at_level(logging.WARNING, logger="micro_engine.engine.prompt_manager"):
        PromptManager(max_tokens=1, estimate_tokens=_words).build_messages(inputs)
    assert any("ceiling" in r.getMessage() for r in caplog.records)


def test_memory_kept_when_budget_allows():
    inputs = PromptInputs(
        identity="id",
        user_message="msg",
        memory_recall="relevant fact",
    )
    messages = _manager(max_tokens=1000).build_messages(inputs)
    assert "relevant fact" in messages[-1]["content"]


# ---------------------------------------------------------------- validation


def test_dialogue_turn_rejects_unknown_role():
    with pytest.raises(ValueError):
        DialogueTurn("system", "nope")
