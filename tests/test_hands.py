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
    read_intention,
)


class _Reader:
    """Стоит за `POST /v0/read`: грамматику читает роутер, здесь — что он ответил и что ему дали."""

    def __init__(self, answer=None) -> None:
        self.answer = answer if answer is not None else {"steps": [], "repeat": 1, "word": None}
        self.texts: list[str] = []

    def __call__(self, text):
        self.texts.append(text)
        return self.answer


class TestReadingHerDecision:
    def test_the_block_goes_to_the_game_and_leaves_the_speech(self):
        # Язык внутри <play> принадлежит игре (28.09): сюда приходит только то, что она
        # поняла, и ни одного слова игры движок не знает.
        read = _Reader(
            {"steps": [{"verb": "build", "object": "shelter"}], "repeat": 1, "word": None}
        )
        intention, speech = read_intention("Okay.<play>\nbuild(shelter)\n</play>", read)
        assert read.texts == ["build(shelter)"]
        assert speech == "Okay."
        assert intention.steps == (Goal("build", {"object": "shelter"}),)

    def test_what_the_game_says_is_one_intention_with_its_repeat(self):
        read = _Reader({
            "steps": [{"verb": "place", "object": "stone"}, {"verb": "dig", "where": {"x": 1}}],
            "repeat": 20,
            "word": None,
        })
        intention, speech = read_intention(
            "watch <play>repeat 20 { place(stone); dig(x: 1) }</play>", read
        )
        assert [g.verb for g in intention.steps] == ["place", "dig"]
        assert intention.steps[1].fields == {"where": {"x": 1}}
        assert intention.repeat == 20
        assert speech == "watch"

    def test_several_blocks_are_read_as_one(self):
        read = _Reader()
        read_intention("a <play>go_to(chest)</play> b <play>put_into(oak_log)</play>", read)
        assert read.texts == ["go_to(chest)\nput_into(oak_log)"]

    def test_a_block_the_game_cannot_read_is_told_back_with_its_reason(self):
        read = _Reader({"error": "line 1, column 5: dig needs parentheses: dig(…)"})
        intention, speech = read_intention("Sure.<play>dig stone</play>", read)
        assert not intention
        assert speech == "Sure."
        assert intention.unread == ("line 1, column 5: dig needs parentheses: dig(…)",)

    def test_an_unclosed_block_is_never_spoken(self):
        # Недописанное решение лучше потерять, чем произнести вслух: живьём 03.09 она
        # ответила игроку строкой «DO: gather "cobblestone" 3 "search": 5» дважды подряд,
        # не сделав при этом ничего.
        read = _Reader()
        intention, speech = read_intention("I am on it.<play>\ngather(cobble", read)
        assert speech == "I am on it."
        assert read.texts == ["gather(cobble"]

    def test_the_old_form_outside_the_block_is_cut_and_told_not_read(self):
        # DO: снят (28.09), но строка протокола, сказанная вслух в чат, хуже несделанного.
        read = _Reader()
        intention, speech = read_intention('Okay.\nDO: gather {"object": "stone"}\nCONTINUE', read)
        assert speech == "Okay."
        assert read.texts == [], "старая форма в игру не уходит"
        assert len(intention.unread) == 2
        assert all("old form" in u for u in intention.unread)

    def test_with_no_game_the_block_is_still_cut(self):
        intention, speech = read_intention("Fine.<play>follow(player Honto)</play>")
        assert not intention
        assert speech == "Fine."

    def test_the_block_is_named_in_what_she_is_told(self):
        # Правило, живущее только в разборе, до пишущего цель не доезжает.
        offer = {
            "game": "Minecraft",
            "about": "",
            "affordances": [{"verb": "gather", "needs": "object"}],
        }
        told = describe(offer, {})
        assert "<play>" in told
        assert "nothing inside it is spoken" in told.lower()
        assert "gather(oak_log, 16)" in told
        assert "DO:" not in told

    def test_do_only_counts_at_the_start_of_a_line(self):
        # Any other rule turns her own "just do: whatever you want" into an order
        # to her body, and no test in which she is obedient would ever show it.
        intention, speech = read_intention("just do: whatever you want", _Reader())
        assert not intention
        assert intention.unread == ()
        assert speech == "just do: whatever you want"


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

    def test_a_nested_list_is_summarised_but_the_census_never_is(self):
        """Живьём 03.09 строка про блоки шла на 589 символов: каждый род печатал
        все свои координаты и потом ПОВТОРЯЛ первую как nearest. Верстак, который
        она собиралась продублировать, был там — и был погребён.

        Режется подробность, а не перепись: выбросить запись снаружи значит
        потерять целую вещь, а не её частности.
        """
        census = [{"what": f"kind{i}", "where": [{"x": n} for n in range(9)]} for i in range(6)]
        said = plainly(census)
        for i in range(6):
            assert f"kind{i}" in said, "род не имеет права пропасть"
        assert "and 6 more" in said, "координаты сокращаются"

    def test_an_empty_reading_is_a_fact_and_a_missing_one_is_not(self):
        """Живьём 03.09 игрок позвал её «в наш дом», а список отмеченных мест был
        пуст — значит про места её промпт не говорил ВООБЩЕ НИЧЕГО, и модель
        заполнила пробел домом, которого нет.

        Та же форма, что у Марии с просмотренным: пропущенный блок дописывается,
        напечатанное «ты не отмечала ничего» — это ответ.
        """
        assert plainly([]) == "none"
        assert plainly({"places": [], "signs": []}) == "places none, signs none"
        # Отсутствующее — по-прежнему ничего: «нет сведений» и «сведения о пустоте»
        # это разные вещи, и вторая не имеет права выглядеть первой.
        assert plainly(None) == ""

    def test_what_was_just_said_is_not_said_again(self):
        one = {"where": [{"x": 1}, {"x": 2}], "nearest": {"x": 1}}
        said = plainly(one)
        assert said.count("x 1") == 1
        assert "nearest" not in said


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
        assert "<play>" in block
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

    def test_a_do_line_she_wrote_wrong_still_never_reaches_the_player(self):
        """The one path that leaked, and the reason it survived a test named
        after it: the existing case wrote a DO line that PARSES.

        An intention is falsy exactly when the line was there and could not be
        read, and that path handed the raw reply back. Live 03.09 she answered a
        player in the game chat with `DO: gather "cobblestone" 3 "search": 5`,
        twice running, having done nothing either time.
        """
        from engine.character import CharacterRuntime

        runtime = object.__new__(CharacterRuntime)
        runtime._hands = None
        wrong = 'a stone pickaxe? obviously!!' + chr(10) + 'DO: gather "cobblestone" 3 "search": 5'
        speech, did = runtime._reach_for_the_game(wrong)
        assert "DO:" not in speech
        assert speech == "a stone pickaxe? obviously!!"
        assert did == ()

    def test_an_unfinished_wanting_reaches_her_with_what_is_left(self):
        """Путь к цели не прямой (§21): игрок берётся за кирку, обнаруживает, что
        нужен верстак, идёт за досками и возвращается. Прямая линия прощает ложное
        «я сделала» — следующий шаг упрётся; ОТХОД не прощает, потому что отход и
        есть то место, где внешнее желание надо держать.
        """
        said = describe(
            {"game": "Minecraft", "affordances": [{"verb": "craft"}]},
            {},
            unfinished={
                "plan": "p1",
                "after": {"verb": "craft", "object": "wooden_pickaxe"},
                "stopped_on": {"verb": "craft", "object": "wooden_pickaxe"},
                "why": "needs a crafting table standing nearby",
                "remaining": [{"verb": "craft", "object": "wooden_pickaxe"}],
            },
        )
        assert "wooden_pickaxe" in said
        assert "not finished" in said
        assert "needs a crafting table" in said
        assert "<play>continue</play>" in said

    def test_nothing_unfinished_says_nothing(self):
        said = describe({"game": "g", "affordances": [{"verb": "craft"}]}, {})
        assert "not finished" not in said

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


@pytest.mark.parametrize("times", [0, None, -3])
def test_zero_or_nonsense_times_means_once(times):
    # "Do this zero times" is a slip, not an intention, and obeying it silently
    # is doing nothing and reporting success.
    read = _Reader({"steps": [{"verb": "place"}], "repeat": times, "word": None})
    intention, _ = read_intention("<play>place()</play>", read)
    assert intention.repeat == 1


class TestWhatTheWorldRefused:
    """One line of history teaches nothing.

    Live 03.09: told that a pig is alive and not a block, she fought one — and two
    turns later asked to `gather pig` again, because by then the only thing she
    could see was the outcome of the last attempt and the refusal had scrolled
    away. A world that answers and is then forgotten is a world that has to
    answer the same thing forever.
    """

    HISTORY = [
        {"goal": {"verb": "gather", "object": "pig"}, "outcome": "foreclosed",
         "foreclosed_by": "pig is alive, not a block"},
        {"goal": {"verb": "fight", "object": "pig"}, "outcome": "reached"},
        {"goal": {"verb": "gather", "object": "iron"}, "outcome": "foreclosed",
         "foreclosed_by": "nothing yields iron"},
    ]

    def test_recent_refusals_survive_a_successful_turn(self):
        from engine.hands import refusals

        said = refusals(self.HISTORY)
        assert any("alive, not a block" in one for one in said)
        assert any("nothing yields iron" in one for one in said)

    def test_the_same_wall_five_times_is_one_fact(self):
        from engine.hands import refusals

        same = [self.HISTORY[0]] * 5
        assert len(refusals(same)) == 1

    def test_newest_first_because_that_is_the_wall_she_is_facing(self):
        from engine.hands import refusals

        assert "iron" in refusals(self.HISTORY)[0]

    def test_they_reach_the_block_she_reads(self):
        from engine.hands import describe, refusals

        block = describe(
            {"game": "X", "affordances": [{"verb": "fight"}]},
            {},
            "",
            refusals(self.HISTORY),
        )
        assert "What the world has refused lately" in block
        assert "alive, not a block" in block

    def test_nothing_refused_adds_no_heading(self):
        from engine.hands import describe

        block = describe({"game": "X", "affordances": [{"verb": "fight"}]}, {}, "", ())
        assert "refused lately" not in block


class TestSomethingSheWasPulledOffOf:
    """An interrupt is a pause and never an outcome, so the next word is hers.

    Live 03.09 she was pulled off cutting wood by her own health and simply
    stopped there — nothing in what she could say meant "carry on" or "forget
    it", so a job half done stayed half done forever.
    """

    def test_continue_and_drop_come_back_as_the_game_s_word(self):
        word = _Reader({"steps": [], "repeat": 1, "word": "continue"})
        carry, speech = read_intention("ugh, fine.<play>continue</play>", word)
        assert carry.carry_on and not carry.let_go
        assert speech == "ugh, fine."

        go, _ = read_intention(
            "not worth it.<play>drop</play>", _Reader({"steps": [], "repeat": 1, "word": "drop"})
        )
        assert go.let_go and not go.carry_on

    def test_they_count_as_an_intention_even_with_no_steps(self):
        # Otherwise "carry on" reads as her saying nothing at all.
        word = _Reader({"steps": [], "repeat": 1, "word": "continue"})
        assert bool(read_intention("<play>continue</play>", word)[0])

    def test_a_paused_attempt_is_named_in_the_block(self):
        from engine.character import _paused_id, _paused_name
        from engine.hands import describe

        sight = {"attempt": "a1", "paused": True}
        history = [{"id": "a1", "goal": {"verb": "gather", "object": "oak_log"}}]
        assert _paused_id(sight) == "a1"

        block = describe(
            {"game": "X", "affordances": [{"verb": "gather"}]},
            sight,
            "",
            (),
            _paused_name(history, "a1"),
        )
        assert "part-way through gather oak_log" in block
        assert "<play>continue</play>" in block and "<play>drop</play>" in block

    def test_an_attempt_that_is_merely_running_is_not_paused(self):
        from engine.character import _paused_id

        # Working and stopped look the same to anybody polling attempts; only
        # `paused` tells them apart, which is why the router reports it.
        assert _paused_id({"attempt": "a1", "paused": False}) == ""

    def test_going_back_wins_over_starting_something_new(self):
        """A turn that says both meant the first: taking a goal would silently
        abandon the thing she just said she wanted to finish."""
        from engine.character import CharacterRuntime

        done: list[str] = []

        class Port:
            def resume(self, attempt_id):
                done.append(f"resume {attempt_id}")

            def abandon(self, attempt_id):
                done.append(f"abandon {attempt_id}")

            def act(self, intention):
                done.append("act")

            def read(self, text):
                gather = {"verb": "gather", "object": "oak_log"}
                return {"steps": [gather], "repeat": 1, "word": "continue"}

        runtime = object.__new__(CharacterRuntime)
        runtime._hands = Port()
        runtime._paused = "a1"

        speech, did = runtime._reach_for_the_game("ok<play>gather(oak_log)\ncontinue</play>")
        assert done == ["resume a1"]
        assert did == ("continue",)
        assert speech == "ok"

    def test_with_nothing_paused_a_bare_continue_does_nothing(self):
        from engine.character import CharacterRuntime

        class Port:
            def act(self, intention):
                raise AssertionError("nothing to act on")

            def read(self, text):
                return {"steps": [], "repeat": 1, "word": "continue"}

        runtime = object.__new__(CharacterRuntime)
        runtime._hands = Port()
        runtime._paused = ""
        speech, did = runtime._reach_for_the_game("sure<play>continue</play>")
        assert did == ()
        assert speech == "sure"


def test_what_came_into_her_bag_stands_next_to_what_she_tried():
    """Живьём 28.09: «I dropped some beef for you» — а мясо уже у неё, и она ищет его на
    земле. Строка сумки стояла среди строк «где ты» и не читалась; теперь она своя."""
    told = describe(
        {"game": "Minecraft", "affordances": [{"verb": "pick_up"}]},
        {"her": {"health": 20}, "bag_lately": ["+3 beef (picked up), 2 s ago"]},
        "gather oak_log — worked",
    )
    assert "What came into your bag or left it lately: +3 beef (picked up), 2 s ago" in told
    assert "bag_lately" not in told, "не дважды: не в свалке «где ты»"
    empty = describe({"game": "Minecraft", "affordances": [{"verb": "pick_up"}]}, {})
    assert "left it lately: nothing lately." in empty
