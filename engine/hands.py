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
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import requests

from engine.game_repair import FailedSource

# The wire contract this client was written against.
CONTRACT = "0.0.1"

# Short on purpose: a turn that blocks on a game is a turn the user waits for.
TIMEOUT = 5.0

# She says what she is doing on its own line; the engine cuts it out before the
# reply is shown, so a decision cannot be read aloud as speech.
# How many records of one kind are spelled out before "and N more". Three, because
# repetition is about a pattern, and a pattern shows in three, not in sixteen.
MOST = 3

# Everything addressed to the game in one block — like a thought for characters that have one.
#
# The block is found anywhere in the text and survives sentence joining: what cuts a line
# into sentences joins neighbouring lines with a space, and the line boundary vanishes
# before anyone looks for it.
#
# An unclosed block takes everything to the end: an unfinished decision is better lost than
# said out loud — exactly the defect that made her answer the player on 03.09 with the line
# «DO: gather …».
_PLAY = re.compile(r"<play>(?P<body>.*?)(?:</play>|\Z)", re.IGNORECASE | re.DOTALL)
# The old form outside a block (`DO: …`, `REPEAT: n`, bare CONTINUE/DROP). Since 28.09 the
# language lives only inside `<play>` and is read by the router, but such a line is still cut
# out of speech: protocol said out loud in chat is worse than undone. She is told
# the line was not read.
_STRAY = re.compile(
    r"^\s*(?:do:.*|repeat:\s*\S*|continue|drop)\s*$", re.IGNORECASE | re.MULTILINE
)


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
    # What she wrote for the game and could not be read, with the reader's reason. Not
    # part of truthiness: an unreadable block is not a decision. Kept because silence
    # about it is what let her write the same malformed line twice running, believing
    # both times that she acted.
    unread: tuple[str, ...] = ()
    # Valid source can contain forward or parameter-bound routine calls. These
    # diagnostics do not change truthiness or prevent saving/submitting steps.
    readiness: tuple[str, ...] = ()
    # A reader refusal retains one private draft for repair, not for execution or speech.
    failed_source: FailedSource | None = None

    def __bool__(self) -> bool:
        return bool(self.steps) or self.carry_on or self.let_go


def split_play(reply: str) -> tuple[str, str, tuple[str, ...]]:
    """What she wrote for the game, what she said, and old-form lines found outside.

    The block is cut out WHOLE and never spoken. Lines of the old form outside it are cut
    too — line-anchored on purpose, so her own "just do: whatever you like" in the middle
    of a sentence stays speech.
    """
    inside = "\n".join(m.group("body").strip() for m in _PLAY.finditer(reply)).strip()
    outside = _PLAY.sub("", reply)
    stray = tuple(m.group(0).strip() for m in _STRAY.finditer(outside))
    speech = _STRAY.sub("", outside).strip()
    # Blank lines left where the decisions were.
    speech = re.sub(r"\n{3,}", "\n\n", speech)
    return inside, speech, stray


def read_intention(
    reply: str, read: Callable[[str], dict[str, Any]] | None = None
) -> tuple[Intention, str]:
    """Cut her decision out of the reply and have the game read it.

    The language inside `<play>` belongs to the game (router `POST /v0/read`, 28.09): this
    side types none of its words, only carries the text and brings back what it means —
    steps, how many times, or a word about the attempt she was pulled off. With nothing
    to read it (`read` is None — no game attached), the block is still cut: a character
    who narrates her play at somebody is worse than one who cannot act.
    """
    text, speech, stray = split_play(reply)
    unread = tuple(
        f"«{line}» is the old form and was not read — write calls inside <play>"
        for line in stray
    )
    if not text or read is None:
        return Intention(unread=unread), speech
    said = read(text)
    if said.get("error"):
        failed = FailedSource.capture(text, said)
        return Intention(unread=unread + (str(failed.diagnostic.get("error", "reader refusal")),),
                         failed_source=failed), speech
    steps = tuple(
        Goal(str(s["verb"]), {k: v for k, v in s.items() if k != "verb"})
        for s in said.get("steps") or []
        if isinstance(s, dict) and s.get("verb")
    )
    word = said.get("word")
    return (
        Intention(
            steps,
            max(1, int(said.get("repeat") or 1)),
            carry_on=word == "continue",
            let_go=word == "drop",
            unread=unread,
            readiness=_readiness_diagnostics(said),
        ),
        speech,
    )


def _readiness_diagnostics(said: dict[str, Any]) -> tuple[str, ...]:
    """Carry optional Router readiness metadata without interpreting its DSL."""
    if said.get("ready") is not False:
        return ()
    calls = said.get("unresolved_calls")
    if not isinstance(calls, list):
        calls = []
    diagnostics = tuple(
        json.dumps(
            {key: call[key] for key in ("name", "step_path", "reason") if key in call},
            ensure_ascii=False,
        )
        for call in calls if isinstance(call, dict)
    )
    return diagnostics or ("ready: false; the reader gave no unresolved call details",)


def _game_result_diagnostic(result: dict[str, Any], status: int | None = None) -> str:
    """Carry the diagnostic into a turn without duplicating the whole action body."""
    fields = (
        "id", "name", "routine_name", "status", "outcome", "error", "code", "why",
        "foreclosed_by", "saved", "step_path", "line", "column", "expected", "received",
        "message", "confirmation",
    )
    diagnostic = {key: result[key] for key in fields if key in result}
    if status is not None:
        diagnostic["http_status"] = status
    return plainly(diagnostic)


class GameRequestRejected(RuntimeError):
    """An explicit Router refusal, distinct from a lost response."""

    def __init__(self, result: dict[str, Any], status: int | None = None) -> None:
        self.result = result
        self.status = status
        super().__init__(_game_result_diagnostic(result, status))


class GameActionNotCompleted(RuntimeError):
    """A delivered request whose returned action already closed without success."""

    def __init__(self, result: dict[str, Any]) -> None:
        self.result = result
        super().__init__(_game_result_diagnostic(result))


def require_game_acceptance(
    result: Any, status: int | None = None, *, release: bool = False
) -> None:
    """Preserve structured refusals before reporting a request as delivered.

    Acceptance only starts an action; the Router still owns its final outcome.
    In-process ports may return None, while HTTP ports return a result record.
    A release (abandon) is answered with the closed record itself: `abandoned`,
    or the outcome a plan had already recorded, is its success, not a failure.
    """
    if isinstance(result, dict) and (
        result.get("error") or result.get("ok") is False or (status and 400 <= status < 500)
    ):
        raise GameRequestRejected(result, status)
    if release:
        return
    if isinstance(result, dict) and result.get("outcome") in {"foreclosed", "abandoned"}:
        raise GameActionNotCompleted(result)


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

    def glossary(self, name: str) -> dict[str, Any]:
        """Read one generated reference article, or the index for an unknown name."""
        from urllib.parse import quote

        return self._get("/glossary?name=" + quote(name, safe=""))

    # ------------------------------------------------------------------ doing

    def read(self, text: str) -> dict[str, Any]:
        """What the game makes of her `<play>` block: `{steps, repeat, word}` or `{error}`."""
        return self._post("/read", {"text": text})

    def take(self, goal: Goal) -> dict[str, Any]:
        return self._post("/attempts", goal.as_wire())

    def plan(self, steps: list[Goal], repeat: int = 1) -> dict[str, Any]:
        return self._post(
            "/plans", {"steps": [g.as_wire() for g in steps], "repeat": repeat}
        )

    def resume(self, attempt_id: str) -> dict[str, Any]:
        return self._post(f"/attempts/{attempt_id}/resume", {})

    def resume_plan(self, plan_id: str) -> dict[str, Any]:
        """Go and finish what was left of a stopped plan.

        The same word as returning to an interrupted attempt: for her it is one and the same
        "keep going", and how it differs inside is the router's business, which starts a new row
        instead of resurrecting the old one.
        """
        return self._post(f"/plans/{plan_id}/resume", {})

    def abandon(self, attempt_id: str) -> dict[str, Any]:
        return self._post(f"/attempts/{attempt_id}/abandon", {})

    def abandon_plan(self, plan_id: str) -> dict[str, Any]:
        """Release an unfinished plan without rewriting its recorded outcome."""
        return self._post(f"/plans/{plan_id}/abandon", {})

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
        # A server failure can leave delivery uncertain. A 4xx response explicitly
        # refuses this request. Reader errors remain data for syntax feedback.
        if r.status_code >= 500:
            r.raise_for_status()
        result = r.json()
        if path != "/read":
            require_game_acceptance(result, r.status_code, release=path.endswith("/abandon"))
        return result


# --------------------------------------------------------------------- saying it

def plainly(value: Any, depth: int = 0, *, unabridged: frozenset[str] = frozenset()) -> str:
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
        said = [p for p in (plainly(v, depth + 1, unabridged=unabridged) for v in value) if p]
        # **An empty list is a FACT, a missing value is not.**
        #
        # Empty read as nothing and was dropped from the prompt entirely. Live 03.09 the player
        # called her "to our house", and the list of marked places was empty — so her prompt said
        # NOTHING AT ALL about places, and the model filled the gap with a house that does not
        # exist. The same shape as Maria's with what she watched: an omitted block gets made up, a
        # printed "you have marked nothing" is an answer.
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
            # A caller may preserve already bounded notifications instead of
            # losing their newest entries behind an ordinary census limit.
            said = plainly(v, 0 if k in unabridged else depth + 1, unabridged=unabridged)
            if not said:
                continue
            # Already said, in this same breath. A STRICT part of something already
            # said: the nearest of a kind is the first of its list, not a separate
            # fact. Strict — because equality is not a repeat but a coincidence:
            # two empty lists give "none" and "none", and those are TWO facts, each about
            # its own thing. A swallowed second one is exactly the silence that makes her
            # invent.
            # VALUES are compared with values, not with the already joined line: that one
            # also holds the key, and "none" turned out to be part of "places none".
            if any(said in earlier and len(said) < len(earlier) for earlier in told):
                continue
            told.append(said)
            out.append(f"{k} {said}")
        return ", ".join(out)
    return str(value)


def describe(
    offer: dict[str, Any],
    sight: dict[str, Any],
    actions: str = "",
    paused: str = "",
    unfinished: dict[str, Any] | None = None,
    notes: str = "",
    effects_in_actions: bool = False,
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

    if offer.get("glossary"):
        return _describe_reference(
            offer, sight, actions, paused, unfinished, notes, effects_in_actions)

    lines = [
        f"You are in {offer.get('game') or 'a world'} and you can act in it yourself. "
        + str(offer.get("about") or "").strip(),
        "",
        "<body>",
        actions or "Recent actions: none observed yet.",
        "Where you are right now:",
    ]
    for key, value in (sight or {}).items():
        if key in ("actions", "ammunition", "noticed", "atlas", "in_hand", "equipment"):
            continue
        if key == 'her' and effects_in_actions:
            value = {name: fact for name, fact in value.items() if name != 'effects'}
        # The equipment block already says what she wears, slot by slot.
        if key == 'her' and (sight or {}).get('equipment'):
            value = {name: fact for name, fact in value.items() if name not in ('wearing', 'bare')}
        said = plainly(value, unabridged=frozenset({"effects", "body_lately"}))
        if said:
            lines.append(f"  {key}: {said}")
    lines += [
        "</body>",
        "",
        # A frame, not character. Yukina's pack is written for roleplay, and in roleplay inventing a
        # detail is the job; in the world it is a lie, and the difference must be declared
        # by whoever
        # brings the world. Live 03.09 the player called her "to our house", and she invented a
        # house: the list of places was empty and never reached her.
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

    # What is in her hand and the keys it has — its own paragraph, like the bag (01.10).
    # Buried in the dump of everything she sees, a flintlock's reload was one line among
    # forty, and she told him «where is the button?» with the button in front of her.
    hand = (sight or {}).get("in_hand")
    if isinstance(hand, dict) and hand.get("keys"):
        lines += [
            "",
            f"In your hand: {hand.get('item')}"
            + (f" — its data: {hand['data']}" if hand.get("data") else "") + ".",
            f"What it does is its keys (press one): {hand['keys']}"
            + (f" (and {hand['more']} more of its mods')" if hand.get("more") else "") + ".",
            "  press(<key>, args: [values in that order]) — a hand is MAIN_HAND or OFF_HAND;",
            "  @self, @yaw, @pitch are filled in for you; a refusal names the values it wants.",
        ]
    # What she noticed far off and her atlas are NOT standing lines (author, 30.09): printed
    # every turn, a statue two hundred blocks away was news again each time and Mizuki
    # talked about it between his lines. A new find arrives once, as its own note
    # (`noticed` in tools/play.py); the atlas stays in the router for her feet.
    if paused:
        # An interrupt is a pause and never an outcome, so the next word is hers —
        # and until now there was no word. Live 03.09 she was pulled off cutting
        # wood by her own health and simply stopped there, because nothing in what
        # she could say meant "carry on" or "forget it".
        lines += [
            "",
            f"You are part-way through {paused} and stopped when something happened.",
            "Write <play>continue</play> to go back to it, or <play>drop</play> to let it go.",
            "Taking a new goal drops it too — that is a choice, not a mistake.",
        ]
    if unfinished:
        # The unfinished wish, and it matters more than the pause.
        #
        # The path to a goal is not straight (§21, the author's note): a player takes up a pickaxe,
        # finds that a crafting table is needed, goes for planks and comes back. A straight line
        # forgives a false "I did it" — the next step will run into it and say so;
        # a DETOUR does not,
        # because a detour is exactly where the outer wish has to be held.
        #
        # And there was nothing to hold it with: the plan closed, the outcome description told about
        # the last attempt, and nobody remembered she was going for a PICKAXE. At that moment the
        # easiest thing for the model is to assume the pickaxe is made.
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
            "for, then write <play>continue</play> to pick this up again.",
        ]
    lines += [
        "",
        "This is a list of what is possible, not a list of things to do. Wanting",
        "none of it is an answer. Everything you say to the game goes in one block",
        "at the end of your reply, and nothing inside it is spoken:",
        "",
        "  <play>",
        "  gather(oak_log, 16)",
        "  follow(player HontoUKI, within: 3)",
        "  </play>",
        "",
        "One call per line, in order. The first argument is what the verb acts on,",
        "the second how many; everything else goes by name — the fields that verb",
        "said it needs, so where.x is x: 5 and where.who is who: HontoUKI.",
        "A place: chest NEAR 8 (by what stands there) or at: (x, y, z).",
        "Things by what they are: ALL or FIRST, then where and EXCEPT —",
        "put_into(ALL where mod == create EXCEPT [tools, food], at: chest NEAR 8).",
        "To do the whole list more than once: repeat 3 { … } around it.",
        "Saying you will go and do something is not doing it: the block is your",
        "hands, and without one nothing moved.",
    ]
    return "\n".join(lines)


def _describe_reference(offer, sight, actions, paused, unfinished, notes, effects_in_actions=False):
    """World sections ordered for truncation: situation, belongings, failures, people, index."""
    sections = [
        f"You are in {offer.get('game') or 'a world'}. "
        "Act only inside <play>...</play>, one call per line. Speech does not move your hands. "
        "Calls request actions; they do not prove success. While submitting a call, "
        "describe your intention, not a completed result. Report success on a later turn "
        "only when current state and outcomes confirm the player's actual request. "
        "A reached craft does not mean the crafted block was placed or handed over. "
        "Use run(name, param: value) for a known routine. "
        "Primitive verbs are direct calls, never run(primitive_name, ...). "
        "Write routines as @teach(details: \"purpose\") def my_routine(item: bread) "
        "{ consume($item) }; declare params in def and use $params in the body. "
        "Send the declaration alone. Only routine_saved with saved: true confirms saving; "
        "routine_rejected means nothing was saved: fix its line and block_path, then resend. "
        "The router compiles before saving. Do not write JSON steps. "
        "<lookup>Glossary</lookup> lists reference topics; <lookup>Teach</lookup> explains "
        "how to save routines, loops and conditions. At most one lookup per turn; "
        "lookup is disabled under threat. Only listed things and places are known. "
        "Wanting none of it is an answer.",
        "<body>\n" + (actions or "Recent actions: none observed yet."),
    ]
    if paused:
        sections.append(f"You are part-way through {paused}. "
                        "<play>continue</play> resumes; <play>drop</play> abandons it.")
    if unfinished:
        sections.append("Unfinished intention: " + plainly(unfinished)
                        + "\n<play>continue</play> retries it; <play>drop</play> releases it "
                        "when you change the plan, including before replacement calls.")
    core = {k: sight[k] for k in ("her", "world", "walking_with", "defending", "mending")
            if k in sight}
    if effects_in_actions and isinstance(core.get('her'), dict):
        core['her'] = {key: value for key, value in core['her'].items() if key != 'effects'}
    sections.append("Your situation:\n" + plainly(
        core, unabridged=frozenset({"effects", "body_lately"})))
    hand = sight.get("in_hand")
    if hand:
        sections.append("In your hand: " + plainly(hand))
    if "inventory" in sight:
        sections.append("Your bag:\n" + plainly(sight["inventory"]))
    for key in ("around", "people", "entities", "bosses"):
        if key in sight:
            sections.append(f"{key}: {plainly(sight[key])}")
    if notes:
        sections.append(notes)
    # Routines are never discarded behind a large terrain dump.
    if "routines" in sight:
        sections.append("Your routines (name, details):\n"
                        + "\n".join(plainly(r) for r in sight["routines"]))
    for key in ("window", "sense", "terrain", "plants_around"):
        if key in sight:
            sections.append(f"{key}: {plainly(sight[key])}")
    skip = {"her", "world", "walking_with", "defending", "mending", "inventory", "in_hand",
            "actions", "ammunition", "equipment", "routines", "noticed", "atlas", "around",
            "people", "entities", "bosses",
            "window", "sense", "terrain", "plants_around"}
    for key, value in sight.items():
        if key not in skip:
            sections.append(f"{key}: {plainly(value)}")
    sections.append('</body>')
    return "\n\n".join(sections)
