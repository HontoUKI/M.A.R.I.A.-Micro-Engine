"""Reaching a game.

The engine talks to a **game router** — a separate process that owns one game
and answers three questions: what do I see, what can I do here, did it work.
The protocol is published (Sponge-style versioned HTTP at `/v0`) and this module
is only the telephone.

Two boundaries hold this in place, and both are deliberate.

**A pack cannot turn this on.** A character pack is data — prompt text and
numbers — and nothing in it may reach the network. Whether a game is attached is
a *deployment* decision (`GAME_PORT`), exactly like the choice of model. Without
that setting there is no game and no character is told there is one; with it,
any character can act, because having hands is a property of where she is
running, not of who she is.

**The vocabulary belongs to the game.** The router declares its own verbs and
what each of them needs; this file types none of them. That is what lets a
second game be attached without a line changing here, and it is why the goal's
`where` travels as opaque JSON.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any

import requests

# The wire contract this client was written against.
CONTRACT = "0.0.1"

# Short on purpose: a turn that blocks on a game is a turn the user waits for.
TIMEOUT = 5.0

# She says what she is doing on its own line; the engine cuts it out before the
# reply is shown, so a decision cannot be read aloud as speech.
# Сколько однородных записей проговаривается прежде «и ещё N». Три, потому что
# повторение — это про рисунок, а рисунок виден на трёх, не на шестнадцати.
MOST = 3

_DO = re.compile(r"^\s*do:\s*(?P<body>.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_REPEAT = re.compile(r"^\s*repeat:\s*(?P<times>\d+)\s*$", re.IGNORECASE | re.MULTILINE)
# Going back to something she was pulled off, or letting it go. Protocol words, not
# game verbs: they are about the ATTEMPT and no game declares them, so they cannot
# collide with a vocabulary the router owns.
_CONTINUE = re.compile(r"^\s*continue\s*$", re.IGNORECASE | re.MULTILINE)
_DROP = re.compile(r"^\s*drop\s*$", re.IGNORECASE | re.MULTILINE)


@dataclass(frozen=True)
class Goal:
    """One thing to do, in the game's own words."""

    verb: str
    fields: dict[str, Any] = field(default_factory=dict)

    def as_wire(self) -> dict[str, Any]:
        return {"verb": self.verb, **self.fields}


@dataclass(frozen=True)
class Intention:
    """What she decided this turn: the steps, and how many times through."""

    steps: tuple[Goal, ...] = ()
    repeat: int = 1
    # What to do about something she was pulled off part-way through. An interrupt is a
    # pause and never an outcome, so the next word is hers — and until now there was no
    # word: she stayed frozen mid-job with no way to say either "carry on" or "forget it".
    carry_on: bool = False
    let_go: bool = False
    # `DO:` lines that were there and could not be read. Not part of truthiness: an
    # unreadable line is not a decision. Kept because silence about it is what let her
    # write the same malformed line twice running, believing both times that she acted.
    unread: tuple[str, ...] = ()

    def __bool__(self) -> bool:
        return bool(self.steps) or self.carry_on or self.let_go


def read_intention(reply: str) -> tuple[Intention, str]:
    """Pull the `DO:` lines out of a reply and hand back what is left to say.

    Line-anchored on purpose. A rule that matched `do:` anywhere would turn her
    own "do: whatever you like" into an order to her body, and no test in which
    she is obedient would ever show it.
    """
    steps: list[Goal] = []
    unread: list[str] = []
    for match in _DO.finditer(reply):
        body = match.group("body")
        goal = read_goal(body)
        if goal is not None:
            steps.append(goal)
        else:
            unread.append(body)

    times = 1
    for match in _REPEAT.finditer(reply):
        times = max(1, int(match.group("times")))

    carry_on = bool(_CONTINUE.search(reply))
    let_go = bool(_DROP.search(reply))
    speech = _DROP.sub("", _CONTINUE.sub("", _REPEAT.sub("", _DO.sub("", reply)))).strip()
    # Blank lines left where the decisions were.
    speech = re.sub(r"\n{3,}", "\n\n", speech)
    return Intention(tuple(steps), times, carry_on, let_go, tuple(unread)), speech


def read_goal(line: str) -> Goal | None:
    """`<verb> {json}` — the verb, then the game's own vocabulary.

    Forgives exactly one thing: a bare second word is read as the object,
    because that is what anyone writes without thinking and refusing it means
    she silently did nothing. It forgives nothing more, because guessing further
    is the vocabulary drift a closed set exists to prevent.
    """
    line = line.strip()
    if not line:
        return None
    verb, _, tail = line.partition(" ")
    tail = tail.strip()
    if not verb:
        return None
    if not tail:
        return Goal(verb)
    if tail.startswith("{"):
        try:
            fields = json.loads(tail)
        except ValueError:
            return None
        return Goal(verb, fields if isinstance(fields, dict) else {})
    if len(tail.split()) == 1:
        return Goal(verb, {"object": tail})
    return None


class GamePort:
    """A game she can reach, over the wire."""

    def __init__(self, base_url: str, *, timeout: float = TIMEOUT) -> None:
        self.base = base_url.rstrip("/")
        self.timeout = timeout

    # ------------------------------------------------------------------ asking

    def contract(self) -> str:
        return str(self._get("/contract").get("contract", ""))

    def reachable(self) -> bool:
        """Worth asking once at start-up and saying out loud: a router that is
        not running looks, from inside, exactly like a game with nothing to do."""
        try:
            return bool(self.contract())
        except Exception:
            return False

    def offer(self) -> dict[str, Any]:
        return self._get("/affordances")

    def sight(self) -> dict[str, Any]:
        return self._get("/state")

    def history(self) -> list[dict[str, Any]]:
        return list(self._get("/attempts").get("attempts", []))

    # ------------------------------------------------------------------ doing

    def take(self, goal: Goal) -> dict[str, Any]:
        return self._post("/attempts", goal.as_wire())

    def plan(self, steps: list[Goal], repeat: int = 1) -> dict[str, Any]:
        return self._post(
            "/plans", {"steps": [g.as_wire() for g in steps], "repeat": repeat}
        )

    def resume(self, attempt_id: str) -> dict[str, Any]:
        return self._post(f"/attempts/{attempt_id}/resume", {})

    def resume_plan(self, plan_id: str) -> dict[str, Any]:
        """Пойти доделывать то, что осталось от вставшего плана.

        Тем же словом, что и возвращение к прерванной попытке: для неё это одно и то же
        «продолжай», а чем оно отличается внутри — дело роутера, который и заводит новый
        ряд вместо воскрешения старого.
        """
        return self._post(f"/plans/{plan_id}/resume", {})

    def abandon(self, attempt_id: str) -> dict[str, Any]:
        return self._post(f"/attempts/{attempt_id}/abandon", {})

    def act(self, intention: Intention) -> dict[str, Any]:
        """Set an intention going. One step once is an attempt; anything else is
        a plan, because "twenty times" is a sequence even when the sequence has
        one step in it."""
        if len(intention.steps) == 1 and intention.repeat == 1:
            return self.take(intention.steps[0])
        return self.plan(list(intention.steps), intention.repeat)

    # ------------------------------------------------------------------ plumbing

    def _get(self, path: str) -> dict[str, Any]:
        r = requests.get(f"{self.base}{path}", timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    def _post(self, path: str, body: dict[str, Any]) -> dict[str, Any]:
        r = requests.post(f"{self.base}{path}", json=body, timeout=self.timeout)
        return r.json()


# --------------------------------------------------------------------- saying it

def plainly(value: Any, depth: int = 0) -> str:
    """Say what the game sent, knowing none of its words.

    Mechanical on purpose. Reading the state by meaning — "health", "around",
    "blocks" — would make the engine know one game, and the second game would
    arrive in the prompt empty while reporting success.

    Two rules keep it readable, and both are about DATA rather than about any
    game. A NESTED list is summarised, because sixteen coordinates of one thing
    are the same fact sixteen times — the outermost list is the census itself
    and is never cut, since dropping an entry there drops a whole thing rather
    than its details. And a value already said in this breath is not said again:
    the world sent every instance of a kind AND its nearest one, which is right
    for a record and doubles the noise in a sentence.

    Live 03.09 the blocks line ran to 589 characters, terrain first, with every
    coordinate printed twice — and the crafting table she was about to duplicate
    was in there, buried. She was not blind; the sentence was unreadable.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, list):
        said = [p for p in (plainly(v, depth + 1) for v in value) if p]
        # **Пустой список — это ФАКТ, а отсутствующее значение — нет.**
        #
        # Пустое читалось как ничего и выбрасывалось из промпта целиком. Живьём 03.09
        # игрок позвал её «в наш дом», а список отмеченных мест был пуст — значит про
        # места её промпт не говорил ВООБЩЕ НИЧЕГО, и модель заполнила пробел домом,
        # которого нет. Та же форма, что у Марии с просмотренным: пропущенный блок
        # дописывается, напечатанное «ты не отмечала ничего» — это ответ.
        if not said:
            return "none"
        if depth > 0 and len(said) > MOST:
            rest = len(said) - MOST
            return "; ".join(said[:MOST]) + f"; and {rest} more"
        return "; ".join(said)
    if isinstance(value, dict):
        out: list[str] = []
        told: list[str] = []
        for k, v in value.items():
            said = plainly(v, depth + 1)
            if not said:
                continue
            # Already said, in this same breath. A STRICT part of something already
            # said: the nearest of a kind is the first of its list, not a separate
            # fact. Строгая — потому что равенство это не повтор, а совпадение:
            # два пустых списка дают «none» и «none», и это ДВА факта, каждый про
            # своё. Проглоченный второй — ровно та тишина, из-за которой она и
            # сочиняет.
            # Сравниваются ЗНАЧЕНИЯ со значениями, а не с уже склеенной строкой: в той
            # стоит ещё и ключ, и «none» оказывалось частью «places none».
            if any(said in earlier and len(said) < len(earlier) for earlier in told):
                continue
            told.append(said)
            out.append(f"{k} {said}")
        return ", ".join(out)
    return str(value)


def describe(
    offer: dict[str, Any],
    sight: dict[str, Any],
    last: str = "",
    lessons: tuple[str, ...] = (),
    paused: str = "",
    unfinished: dict[str, Any] | None = None,
) -> str:
    """The block that tells her she has hands, and what they can do.

    The game supplies **names**: what its verbs are called, what each needs, and
    a sentence about itself. How to choose, what form an answer takes, and her
    right to want none of it are the engine's words — text arriving from another
    process and landing in a prompt as instructions is a channel for putting
    words in somebody's head, and it stays closed by construction rather than by
    trusting whoever wrote the adapter.
    """
    verbs = offer.get("affordances") or []
    if not verbs:
        return ""

    lines = [
        f"You are in {offer.get('game') or 'a world'} and you can act in it yourself. "
        + str(offer.get("about") or "").strip(),
        "",
        "Where you are right now:",
    ]
    for key, value in (sight or {}).items():
        said = plainly(value)
        if said:
            lines.append(f"  {key}: {said}")
    lines += [
        "",
        # Рамка, а не характер. Пак Юкины писан под отыгрыш, а в отыгрыше придумать
        # подробность — это работа; в мире это враньё, и разницу должен объявить тот,
        # кто мир приносит. Живьём 03.09 игрок позвал её «в наш дом», и она сочинила
        # дом: список мест был пуст и до неё не доезжал вовсе.
        "Everything above is what you actually see and remember. It is not a"
        " setting to embellish: a place that is not listed is one you have not"
        " marked, and a thing not listed is one you have not seen. Saying where"
        " something is when it is not above is making it up. Not knowing is an"
        " ordinary answer, and it is the one that gets you taken there.",
        "",
        "What you can do, and what each needs:",
    ]
    for one in verbs:
        needs = str(one.get("needs") or one.get("predicate") or "").strip()
        lines.append(f"  {one.get('verb')}" + (f" — {needs}" if needs else ""))

    lines += [
        "",
        f"The last thing you tried: {last or 'nothing yet.'}",
    ]
    if paused:
        # An interrupt is a pause and never an outcome, so the next word is hers —
        # and until now there was no word. Live 03.09 she was pulled off cutting
        # wood by her own health and simply stopped there, because nothing in what
        # she could say meant "carry on" or "forget it".
        lines += [
            "",
            f"You are part-way through {paused} and stopped when something happened.",
            "Say CONTINUE on its own line to go back to it, or DROP to let it go.",
            "Taking a new goal drops it too — that is a choice, not a mistake.",
        ]
    if unfinished:
        # Незаконченное желание, и оно важнее паузы.
        #
        # Путь к цели не прямой (§21, замечание автора): игрок берётся за кирку,
        # обнаруживает, что нужен верстак, идёт за досками и возвращается. Прямая линия
        # прощает ложное «я сделала» — следующий шаг упрётся и скажет; ОТХОД не прощает,
        # потому что отход ровно то место, где внешнее желание надо держать.
        #
        # А держать было нечем: план закрывался, `how_it_went` рассказывал про последнюю
        # попытку, и то, что она шла за КИРКОЙ, не помнил никто. Проще всего модели в
        # этот момент считать, что кирка сделана.
        after = plainly(unfinished.get("after"))
        stopped = plainly(unfinished.get("stopped_on"))
        left = unfinished.get("remaining") or []
        lines += [
            "",
            f"You set out to {after} and have not finished.",
            f"It stopped on: {stopped}"
            + (f" — {unfinished['why']}" if unfinished.get("why") else ""),
            f"Still to do, in order: {plainly(left)}",
            "Doing something else first is how this usually goes — make what it asked",
            "for, then say CONTINUE on its own line to pick this up again.",
        ]
    if lessons:
        # What the world has refused, kept for a few turns.
        #
        # One line of history teaches nothing. Live 03.09: told that a pig is
        # alive and not a block, she fought one — and two turns later asked to
        # `gather pig` again, because by then the only thing she could see was
        # the outcome of the last attempt and the refusal had scrolled away. A
        # world that answers and is then forgotten is a world that has to answer
        # the same thing forever.
        lines += ["", "What the world has refused lately:"]
        lines += [f"  {one}" for one in lessons]
    lines += [
        "",
        "This is a list of what is possible, not a list of things to do. Wanting",
        "none of it is an answer. When you do decide to act, put it on its own",
        "line at the end, one line per step:",
        "",
        '  DO: <verb> {"object": "...", "where": {...}}',
        "",
        "The JSON answers what that verb said it needs. To do the whole list more",
        "than once, add REPEAT: <n> after the DO lines. Saying you will go and do",
        "something is not doing it — the DO line is your hands, and without one",
        "nothing moved.",
    ]
    return "\n".join(lines)


def refusals(attempts: list[dict[str, Any]], most: int = 3) -> tuple[str, ...]:
    """The last few distinct things the world said no to.

    Distinct, because the same refusal five times running is one fact and four
    wasted lines. Newest first, because the most recent wall is the one she is
    standing in front of.
    """
    seen: list[str] = []
    for attempt in reversed(attempts or []):
        why = attempt.get("foreclosed_by")
        if not why:
            continue
        goal = attempt.get("goal") or {}
        what = goal.get("object")
        said = f"{goal.get('verb')}{f' {plainly(what)}' if what else ''} — {why}"
        if said not in seen:
            seen.append(said)
        if len(seen) >= most:
            break
    return tuple(seen)


def how_it_went(attempts: list[dict[str, Any]]) -> str:
    """What became of the last thing she actually tried.

    `take` returns while the attempt is still running, so on her own turn there
    is no answer yet: only the next turn can say whether it worked, and it has
    to say it in words or she learns of the world's refusal from nowhere.
    """
    for attempt in reversed(attempts or []):
        outcome = attempt.get("outcome")
        if not outcome:
            continue
        goal = attempt.get("goal") or {}
        what = goal.get("object")
        named = f" {plainly(what)}" if what else ""
        if any(e.get("kind") == "already" for e in attempt.get("events") or []):
            return f"{goal.get('verb')}{named} — nothing to do, it was already true"
        if outcome == "reached":
            return f"{goal.get('verb')}{named} — worked"
        if outcome == "abandoned":
            return f"{goal.get('verb')}{named} — you dropped it"
        why = attempt.get("foreclosed_by")
        return f"{goal.get('verb')}{named} — the world said no" + (f": {why}" if why else "")
    return ""
