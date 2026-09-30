"""What has already been said between them — so it is not asked or said again.

Live 29.09 (Mizuki): three questions about his goggles in two minutes, the first two
unanswered; «Дома я бы тебе объяснила…» five times in twenty minutes; «Ты всё равно
меня не слушаешь» three times. The window is eight messages, and the world's own notes
(«he is standing with a pig», «[closed]») take their places in it, so her own words
leave it in a minute or two. What is gone from the window she can say again as if new.

The author's idea: keep «mentioned» records. Built from her OWN lines and nothing
else — no model call, no summary: a question is a sentence of hers that ends in «?»,
its answer is his very next turn if he spoke in it (a world note is not an answer), and
a statement is any other sentence of hers long enough to be a formula. Deterministic,
so a record never says what was not said.
"""

from __future__ import annotations

import re

#: How many recent turns are read. A longer memory is the dossier's job.
LOOK_BACK = 40
#: At most this many questions and this many statements are printed.
MOST_ASKED = 8
MOST_SAID = 6
#: A line is quoted up to this many characters.
QUOTE = 90
#: Shorter sentences («Иду!», «Спасибо.») are not formulas worth remembering.
SHORTEST = 18
#: His answer is his very next turn, and only if he spoke in it. Two turns on, with a
#: world note between, «Ты не от мира сего» was filed as the answer to «А он кислый?».
ANSWER_WITHIN = 1

_SENTENCE = re.compile(r"[^.!?…]+[.!?…]*")
_CHAT = re.compile(r"^<[^>]+>\s*")


def _sentences(text: str) -> list[str]:
    out = []
    for line in str(text or "").splitlines():
        for piece in _SENTENCE.findall(line):
            piece = piece.strip()
            if piece:
                out.append(piece)
    return out


def _quote(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= QUOTE else text[: QUOTE - 1].rstrip() + "…"


def _key(text: str) -> str:
    return re.sub(r"\W+", " ", text.lower()).strip()


def _his_answer(entries: list[dict], after: int) -> str | None:
    """His next chat line within ANSWER_WITHIN turns, without the «<name>» label."""
    for entry in entries[after + 1 : after + 1 + ANSWER_WITHIN]:
        said = str(entry.get("user") or "")
        if _CHAT.match(said):
            return _CHAT.sub("", said).strip() or None
    return None


def mentioned(entries: list[dict]) -> str:
    """One tail line: what she already asked (and what he answered) and already said."""
    recent = list(entries or [])[-LOOK_BACK:]
    asked: list[str] = []
    said: list[str] = []
    seen: set[str] = set()
    # Newest first: when the list is cut, the old end goes.
    for i in range(len(recent) - 1, -1, -1):
        questions = []
        for sentence in reversed(_sentences(recent[i].get("reply"))):
            key = _key(sentence)
            if not key or key in seen:
                continue
            seen.add(key)
            if sentence.endswith("?"):
                questions.insert(0, _quote(sentence))
            elif len(sentence) >= SHORTEST and len(said) < MOST_SAID:
                said.append(f"«{_quote(sentence)}»")
        # One reply's questions are one question asked: they share his one answer.
        if questions and len(asked) < MOST_ASKED:
            answer = _his_answer(recent, i)
            asked.append(
                f"«{' '.join(questions)}» — he said «{_quote(answer)}»" if answer
                else f"«{' '.join(questions)}» — no answer; he heard it"
            )
    if not asked and not said:
        return ""
    parts = ["Already between you — do not ask it again and do not say it again in other words;"
             " if it matters, move on from it:"]
    if asked:
        parts.append("you asked " + "; ".join(asked) + ".")
    if said:
        parts.append("You already said " + "; ".join(said) + ".")
    return " ".join(parts)
