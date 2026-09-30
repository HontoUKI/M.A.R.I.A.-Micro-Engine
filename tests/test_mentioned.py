"""What has already been said between them (engine/mentioned.py), 30.09."""

from engine.mentioned import mentioned


def turn(user, reply):
    return {"user": user, "reply": reply}


def test_nothing_said_nothing_printed():
    assert mentioned([]) == ""
    assert mentioned([turn("<Honto> hi", "Hi.")]) == ""


def test_a_question_carries_his_next_line_or_no_answer():
    lived = [
        turn("<Honto> walk", "Иду. А что это за очки у тебя на лбу? Они что-то меняют?"),
        turn("[closed]", "Просто... А что это за очки у тебя на лбу?"),
        turn("<Honto> Скорее для информации", "Информации о чём?"),
    ]
    told = mentioned(lived)
    # 29.09: the first two were unanswered — a world note is not his answer. The same
    # sentence twice is one record, the newest, which he did answer.
    assert "«А что это за очки у тебя на лбу?» — he said «Скорее для информации»" in told
    assert "«Они что-то меняют?» — no answer; he heard it" in told
    assert told.count("А что это за очки у тебя на лбу?") == 1
    assert "«Информации о чём?» — no answer" in told


def test_answer_is_only_the_very_next_turn():
    lived = [
        turn("<Honto> lemon", "А он кислый?"),
        turn("[closed]", "Ой, прости, я опять встала у тебя на пути."),
        turn("<Honto> Ты не от мира сего", "Ну... технически так и есть."),
    ]
    assert "«А он кислый?» — no answer; he heard it" in mentioned(lived)


def test_formulas_she_already_said_are_listed_short_ones_are_not():
    lived = [turn("<Honto> x", "Дома я бы тебе быстро объяснила, кто тут скучный. Иду!")]
    told = mentioned(lived)
    assert "You already said «Дома я бы тебе быстро объяснила, кто тут скучный.»" in told
    assert "Иду" not in told


def test_newest_first_and_capped():
    lived = [turn(f"<Honto> q{i}", f"Вопрос номер {i}?") for i in range(20)]
    told = mentioned(lived)
    assert "Вопрос номер 19?" in told and "Вопрос номер 11?" not in told
