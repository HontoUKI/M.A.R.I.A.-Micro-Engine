"""Reaching a game from the community tier.

Two boundaries are what these tests are actually about, and they are worth more
than the plumbing they check:

- a character **pack** cannot turn this on. Whether a game is attached is a
  deployment decision, so a pack stays data — prompt text and numbers — and no
  published character can reach the network because somebody wrote a clever
  YAML file.
- the **vocabulary belongs to the game**. The engine types none of its verbs,
  which is what lets a second game be attached with nothing changed here.
"""
from __future__ import annotations

import pytest

from engine.hands import (
    Goal,
    Intention,
    describe,
    how_it_went,
    plainly,
    read_goal,
    read_intention,
)


class TestReadingHerDecision:
    def test_a_do_line_leaves_the_speech(self):
        intention, speech = read_intention('Okay.\nDO: build {"object": "shelter"}')
        assert speech == "Okay."
        assert intention.steps == (Goal("build", {"object": "shelter"}),)

    def test_several_lines_are_one_intention(self):
        intention, _ = read_intention("Fine.\nDO: go_to\nDO: gather\nDO: put_into")
        assert [g.verb for g in intention.steps] == ["go_to", "gather", "put_into"]

    def test_repeat_says_how_many_times(self):
        intention, speech = read_intention("watch\nDO: place stone\nREPEAT: 20")
        assert intention.repeat == 20
        assert speech == "watch"

    def test_do_only_counts_at_the_start_of_a_line(self):
        # Any other rule turns her own "just do: whatever you want" into an order
        # to her body, and no test in which she is obedient would ever show it.
        intention, speech = read_intention("just do: whatever you want")
        assert not intention
        assert speech == "just do: whatever you want"

    def test_a_bare_second_word_is_the_object(self):
        assert read_goal("gather oak_log") == Goal("gather", {"object": "oak_log"})

    def test_prose_is_refused_rather_than_guessed_at(self):
        # Guessing further is the vocabulary drift a closed set exists to prevent.
        assert read_goal("gather some wood from over there") is None
        assert read_goal("gather {oops") is None

    def test_the_game_s_own_words_pass_through_untouched(self):
        goal = read_goal('equip {"object":"helm","where":{"slot":"head"}}')
        assert goal.fields["where"] == {"slot": "head"}


class TestSayingWhatTheGameSent:
    def test_the_engine_knows_none_of_the_keys(self):
        # Reading state by meaning would make the engine know ONE game, and the
        # second game would arrive in the prompt empty while reporting success.
        said = plainly({"her": {"health": 20}, "signs": [{"says": "For Yukina"}]})
        assert "health 20" in said
        assert "For Yukina" in said

    def test_empty_is_not_printed(self):
        # An empty key in a prompt is a line with nothing to learn from and a
        # space somebody may fill in themselves.
        assert "nothing" not in plainly({"nothing": None, "here": 1})


class TestWhatSheIsTold:
    OFFER = {
        "game": "Minecraft",
        "about": "An open world made of blocks.",
        "affordances": [{"verb": "build", "needs": "object — which plan"}],
    }

    def test_the_game_supplies_names_and_the_engine_the_framing(self):
        block = describe(self.OFFER, {"her": {"health": 20}})
        assert "Minecraft" in block and "build" in block
        # Framing is the engine's, not the game's: text arriving from another
        # process and landing in a prompt as instructions is a channel for
        # putting words in somebody's head.
        assert "DO:" in block
        assert "Wanting" in block and "none of it is an answer" in block

    def test_a_game_with_no_verbs_produces_no_block(self):
        # "There is a game and nothing to do in it" is a lie of the kind that
        # gets answered confidently.
        assert describe({"game": "X", "affordances": []}, {}) == ""


class TestDidItWork:
    def test_the_answer_arrives_next_turn_in_words(self):
        assert "worked" in how_it_went([{"goal": {"verb": "gather"}, "outcome": "reached"}])

    def test_a_refusal_carries_its_reason(self):
        said = how_it_went(
            [{"goal": {"verb": "gather"}, "outcome": "foreclosed", "foreclosed_by": "none near"}]
        )
        assert "the world said no: none near" in said

    def test_already_true_does_not_read_as_work_done(self):
        said = how_it_went(
            [{"goal": {"verb": "gather"}, "outcome": "reached", "events": [{"kind": "already"}]}]
        )
        assert "already true" in said

    def test_an_attempt_still_running_is_not_an_answer(self):
        assert how_it_went([{"goal": {"verb": "gather"}, "outcome": None}]) == ""


class TestTheBoundary:
    def test_no_game_attached_means_no_block_and_no_leak(self, monkeypatch):
        """With nothing attached she is told nothing — and her DO line is still
        cut out, because a character who narrates `DO:` at somebody is worse
        than one who simply cannot act."""
        from engine.character import CharacterRuntime

        runtime = object.__new__(CharacterRuntime)
        runtime._hands = None
        assert runtime._game_block() == ""
        speech, did = runtime._reach_for_the_game("Sure.\nDO: build {}")
        assert speech == "Sure."
        assert did == ()

    def test_a_router_that_stopped_answering_is_silence_not_a_stale_world(self):
        from engine.character import CharacterRuntime

        class Dead:
            def offer(self):
                raise ConnectionError("nobody there")

        runtime = object.__new__(CharacterRuntime)
        runtime._hands = Dead()
        assert runtime._game_block() == ""


def test_one_step_once_is_an_attempt_and_anything_else_is_a_plan():
    """"Twenty times" is a sequence even when the sequence has one step in it."""
    from engine.hands import GamePort

    calls: list[tuple[str, object]] = []

    port = GamePort("http://x/v0")
    port.take = lambda goal: calls.append(("take", goal))  # type: ignore[method-assign]
    port.plan = lambda steps, repeat=1: calls.append(("plan", repeat))  # type: ignore[method-assign]

    port.act(Intention((Goal("go_to"),), 1))
    port.act(Intention((Goal("place"),), 20))
    port.act(Intention((Goal("place"), Goal("gather")), 1))

    assert [c[0] for c in calls] == ["take", "plan", "plan"]
    assert calls[1][1] == 20


@pytest.mark.parametrize("times", ["0", "nope", "-3"])
def test_zero_or_nonsense_times_means_once(times):
    # "Do this zero times" is a slip, not an intention, and obeying it silently
    # is doing nothing and reporting success.
    intention, _ = read_intention(f"DO: place\nREPEAT: {times}")
    assert intention.repeat == 1
