"""What has already been said between them (engine/mentioned.py), 30.09."""

from engine.mentioned import mentioned


def turn(user, reply):
    return {"user": user, "reply": reply}


def test_nothing_said_nothing_printed():
    assert mentioned([]) == ""
    assert mentioned([turn("<Honto> hi", "Hi.")]) == ""


def test_a_question_carries_his_next_line_or_no_answer():
    lived = [
        turn("<Honto> walk", "Coming. What are those goggles on your forehead? Do they change anything?"),
        turn("[closed]", "Just... What are those goggles on your forehead?"),
        turn("<Honto> Mostly for information", "Information about what?"),
    ]
    told = mentioned(lived)
    # 29.09: the first two were unanswered — a world note is not his answer. The same
    # sentence twice is one record, the newest, which he did answer.
    assert "«What are those goggles on your forehead?» — he said «Mostly for information»" in told
    assert "«Do they change anything?» — no answer; he heard it" in told
    assert told.count("What are those goggles on your forehead?") == 1
    assert "«Information about what?» — no answer" in told


def test_answer_is_only_the_very_next_turn():
    lived = [
        turn("<Honto> lemon", "Is it sour?"),
        turn("[closed]", "Oh, sorry, I got in your way again."),
        turn("<Honto> You're not of this world", "Well... technically that's true."),
    ]
    assert "«Is it sour?» — no answer; he heard it" in mentioned(lived)


def test_formulas_she_already_said_are_listed_short_ones_are_not():
    lived = [turn("<Honto> x", "At home I'd quickly explain who's boring around here. Coming!")]
    told = mentioned(lived)
    assert "You already said «At home I'd quickly explain who's boring around here.»" in told
    assert "Coming" not in told


def test_newest_first_and_capped():
    lived = [turn(f"<Honto> q{i}", f"Question number {i}?") for i in range(20)]
    told = mentioned(lived)
    assert "Question number 19?" in told and "Question number 11?" not in told
