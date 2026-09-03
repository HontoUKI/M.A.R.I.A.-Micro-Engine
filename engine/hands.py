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
_DO = re.compile(r"^\s*do:\s*(?P<body>.+?)\s*$", re.IGNORECASE | re.MULTILINE)
_REPEAT = re.compile(r"^\s*repeat:\s*(?P<times>\d+)\s*$", re.IGNORECASE | re.MULTILINE)


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

    def __bool__(self) -> bool:
        return bool(self.steps)


def read_intention(reply: str) -> tuple[Intention, str]:
    """Pull the `DO:` lines out of a reply and hand back what is left to say.

    Line-anchored on purpose. A rule that matched `do:` anywhere would turn her
    own "do: whatever you like" into an order to her body, and no test in which
    she is obedient would ever show it.
    """
    steps: list[Goal] = []
    for match in _DO.finditer(reply):
        goal = read_goal(match.group("body"))
        if goal is not None:
            steps.append(goal)

    times = 1
    for match in _REPEAT.finditer(reply):
        times = max(1, int(match.group("times")))

    speech = _REPEAT.sub("", _DO.sub("", reply)).strip()
    # Blank lines left where the decisions were.
    speech = re.sub(r"\n{3,}", "\n\n", speech)
    return Intention(tuple(steps), times), speech


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

def plainly(value: Any) -> str:
    """Say what the game sent, knowing none of its words.

    Mechanical on purpose. Reading the state by meaning — "health", "around",
    "blocks" — would make the engine know one game, and the second game would
    arrive in the prompt empty while reporting success.
    """
    if value is None:
        return ""
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, (int, float, str)):
        return str(value)
    if isinstance(value, list):
        return "; ".join(p for p in (plainly(v) for v in value) if p)
    if isinstance(value, dict):
        return ", ".join(
            f"{k} {said}" for k, v in value.items() if (said := plainly(v))
        )
    return str(value)


def describe(
    offer: dict[str, Any],
    sight: dict[str, Any],
    last: str = "",
    lessons: tuple[str, ...] = (),
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
    lines += ["", "What you can do, and what each needs:"]
    for one in verbs:
        needs = str(one.get("needs") or one.get("predicate") or "").strip()
        lines.append(f"  {one.get('verb')}" + (f" — {needs}" if needs else ""))

    lines += [
        "",
        f"The last thing you tried: {last or 'nothing yet.'}",
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
