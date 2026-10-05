"""Play with her in the game's own chat.

This is the difference between this engine's game support and the one in the
private runtime it came from. There, a player cannot address the character's
body at all — you talk to her elsewhere and she decides. Here the chat IS the
interface: you type in Minecraft, she answers in Minecraft, and the same closed
tag set that steers her voice steers her hands.

It runs beside the server rather than inside it, and that is deliberate. The
HTTP app is a request/response surface; a companion sitting in a chat is a long
loop that outlives any request. Keeping them apart means neither one has to
pretend to be the other.

    make play                          # the character named by CHARACTER in .env
    python tools/play.py --character yukina   # or name one for this run

The router is not started here, for the reason it is not started anywhere: it
attaches to a world somebody is already running.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contracts import ChatMessage  # noqa: E402
from app.deps import get_service  # noqa: E402
from engine.config import load_settings  # noqa: E402

# How much of a conversation she carries between lines. Small on purpose: chat
# lines are short, and a window measured in messages rather than tokens is the
# honest unit for a place where people type "k".
WINDOW = 8

# How long to wait before trying to connect to the stream again. Seconds, not an instant:
# the router is restarted by hand, and hammering a closed port is noise, not readiness.
RECONNECT_EVERY = 3.0

# Events that deserve a turn for her.
#
# Long work gives her no turn at all: the mine says "found iron ore", and next time she is
# asked is when the mine ends. Everything the author listed as "the right choice" — dig out
# a vein, light a cave, clear a dungeon — runs into not a lack of judgement but a lack of a
# MOMENT when it can be spoken.
#
# The list is short and structural, not a matter of taste: the work ended · the work goes on
# by itself and the body is free · she was knocked off · and what she met on the way. Erring
# here is cheap — the player is nearby and will correct it; spamming is costly, hence the threshold.
WAKING = ("closed", "waiting", "interrupted")

# Occasions that carry THEIR OWN content.
#
# Until now there was exactly one event about him — he spoke — and everything else by which a
# person is present never reached her. He came up and watches her build; he put a diamond in
# her hands; he went over the hill; there is a creeper behind his back. A character that has
# all this in its tags could not choose them even once without this wire: the mechanism is
# built and never reaches the moment — that very recurring shape.
#
# The number is how many seconds of quiet after HIS line this occasion needs. Zero for almost
# all, and that is not carelessness: `QUIET_AFTER_HIM` keeps her own business from
# interrupting the conversation, while here the occasion is the conversation itself, only not
# in words. Answering a gifted diamond a second after "take this" is not interrupting him but hearing him.
#
# The exception is a gaze: he may stand and look in the middle of a conversation, and "you're
# looking at me!" over his own line is exactly the old defect.
#
# Death is here too, though it is not about him: without content only an empty bracket is
# left of it, and "she died" and "YOU killed her" are different news, and the second must not be lost.
# The game's own words for each advancement tier — the same three verbs vanilla prints,
# and BlazeandCave's pack prints through its tellraw. The tier is a fact of the
# announcement, not a reading of it.
VERB = {
    "task": "has made the advancement",
    "goal": "has reached the goal",
    "challenge": "has completed the challenge",
}

WITH_CONTENT = {
    "given": 0.0,
    "picked_up_his": 0.0,
    "at_risk": 0.0,
    "left": 0.0,
    "returned": 0.0,
    "beside": 0.0,
    "died": 0.0,
    # He (or another player) died — by the game's own announcement (30.09). Without this, ten
    # seconds after his death she asked "where did you go?". Zero and over everything.
    "player_died": 0.0,
    # Everything that happens to their agreement to walk together. Until now the posture lived
    # silently: she said "I'm following you", fell behind, lost sight of him and stopped being his
    # companion — and not one of these three things reached her. "I'm coming" stayed true exactly
    # until the second it stopped being so.
    "falling_behind": 0.0,
    "lost_sight": 0.0,
    "lost_them": 0.0,
    "cannot_reach": 0.0,
    # He progressed through the game, and the world announced it out loud — to both. Her clock:
    # unease grows not from a mood but from how far he has got.
    "advanced": 0.0,
    # She was hit, and the body is already running (router, `flee.js`: the posture of one who cannot fight).
    # Zero and over his line: a cry for help does not wait for a pause in the conversation.
    "fled": 0.0,
    "watched": None,  # None — keep the common quiet threshold
    # She noticed something made, not grown, in the distance (30.09). Once per find: as a constant
    # line in every turn a statue two hundred blocks away was news again and again. The common
    # quiet threshold — not over his line.
    "noticed": None,
    # She is back where something happened (30.09, router memories.js): "I was hit here", "he
    # almost got caught here". Once per return, not over him.
    "remembered": None,
}

# No more often than once in this many seconds. A turn that cannot be interrupted and comes
# every two seconds is no longer attention but chatter.
WAKE_EVERY = 20.0

# And no sooner than this many seconds after HIS line.
#
# Live 08.09, from her own transcript: he wrote "take some cooked cod", she answered at
# 19:35:00 — and at 19:35:02 took the floor herself, because an attempt closed. The pause
# between her answer and her own "Hellooo? Are you even listening to me?" — TWO SECONDS.
#
# The queue to speak had only one threshold, and the wrong one: "no more than once in twenty
# seconds" counts from her last turn and knows nothing about what he has just said. While
# she stood in the `gather → craft → gather` dead end, attempts closed every few seconds,
# and each gave her the floor over the conversation.
QUIET_AFTER_HIM = 45.0

# While she runs, the calm occasions are silent. Live 30.09 a vex was chasing her, and between
# two "help"s came the note "I see a building in the distance" — the turn went to it, not the chase.
# This many seconds after the last `fled` (my number); the chase itself, a blow and death
# always go through.
DANGER_HOLD = 20.0

# What waits until the danger passes: finds, memory of a place, a gaze and her work.
CALM = frozenset({"noticed", "remembered", "watched", *WAKING})

# How long the queue of picked-up things lives (decided 30.09). Live after his death she
# picked up his things from place to place, and EVERY pickup was a separate turn: five
# "thanks" in thirty seconds. Pickups pile up; if he spoke meanwhile, all of it is described
# in one note before his line, in the same turn. If he stayed silent, it goes as one occasion.
GIFTS_LIVE = 10.0

# How often the loop wakes without events so the queue can expire: the router's stream has
# no pulse, and silence in the world would otherwise hold gifts indefinitely.
TICK = 1.0

# Minecraft chat is one line. Anything longer is sent as several messages rather
# than truncated, because a companion cut off mid-sentence reads as broken.
LINE = 220


def _say(port: str, text: str) -> None:
    for chunk in _chunks(text, LINE):
        body = json.dumps({"text": chunk}).encode()
        request = urllib.request.Request(
            f"{port}/say", data=body, headers={"content-type": "application/json"}
        )
        try:
            urllib.request.urlopen(request, timeout=5).close()
        except OSError as why:
            print(f"[did not say: {why}]", file=sys.stderr)


def _chunks(text: str, limit: int) -> list[str]:
    """Split on whitespace, never mid-word."""
    words, out, line = text.split(), [], ""
    for word in words:
        if len(line) + len(word) + 1 > limit and line:
            out.append(line)
            line = word
        else:
            line = f"{line} {word}".strip()
    if line:
        out.append(line)
    return out or [""]


def _listen(port: str):
    """Yield events off the router's stream, reconnecting when it drops.

    The stream is the only way to hear the world speak first. Polling would work
    for state and cannot work for this: somebody typing is an instant, and an
    instant you sample for is an instant you miss.
    """
    quiet = False
    while True:
        try:
            with urllib.request.urlopen(f"{port}/events", timeout=None) as stream:
                quiet = False
                for raw in stream:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        yield json.loads(line[5:].strip())
                    except ValueError:
                        continue
        except (OSError, urllib.error.URLError) as why:
            # Come back rather than exit: the docstring promised this from the start, while the code
            # did the opposite — live 03.09 a router restart killed her for good, and she stayed
            # silent in a world where the player kept writing to her. The router is a separate
            # process; its restart is not an event in her life.
            if not quiet:
                print(f"[lost the connection to the router: {why} — waiting]", file=sys.stderr)
            quiet = True
            time.sleep(RECONNECT_EVERY)
            continue
        # The stream ended without an error: a break too, just a polite one.
        if not quiet:
            print("[the stream ended — waiting]", file=sys.stderr)
        quiet = True
        time.sleep(RECONNECT_EVERY)


def _ticking(events, every: float = TICK):
    """The same events, plus a ``None`` every ``every`` seconds of silence.

    The stream is read on its own thread: a blocking read cannot notice that a queue
    ran out while nothing happened in the world.
    """
    import queue
    import threading

    box: queue.Queue = queue.Queue()

    def pump() -> None:
        for event in events:
            box.put(event)

    threading.Thread(target=pump, daemon=True).start()
    while True:
        try:
            yield box.get(timeout=every)
        except queue.Empty:
            yield None


# What she picks up is held and folded (`Gifts`): a gift from him, and his things she
# picked up after he died — two different facts, never one list.
PICKUPS = ("given", "picked_up_his")


class Gifts:
    """What she picked up lately, per person and per kind, for ``GIFTS_LIVE`` seconds.

    One pickup is not a moment worth a turn when there are twenty of them: the
    queue folds them into one list, counted by item, in the order they came.
    """

    def __init__(self, live: float = GIFTS_LIVE) -> None:
        self.live = live
        self._by: dict[tuple[str, str], tuple[float, dict[str, int]]] = {}

    def add(self, who: str, took: list[dict], now: float, kind: str = "given") -> None:
        since, items = self._by.get((kind, who), (now, {}))
        for one in took or []:
            what = str(one.get("what") or "something")
            items[what] = items.get(what, 0) + int(one.get("count") or 1)
        self._by[(kind, who)] = (since, items)

    def take(self, who: str) -> list[dict]:
        """Everything queued about ``who``, as folded events — he is talking to her."""
        return [self._out(key) for key in [key for key in self._by if key[1] == who]]

    def due(self, now: float) -> list[dict]:
        """Queues that lived out their time, as folded events, removed."""
        keys = [key for key, (since, _) in self._by.items() if now - since >= self.live]
        return [self._out(key) for key in keys]

    def _out(self, key: tuple[str, str]) -> dict:
        _, items = self._by.pop(key)
        return {"kind": key[0], "who": key[1], "took": _took(items), "folded": True}


def _took(items: dict[str, int]) -> list[dict]:
    return [{"what": what, "count": count} for what, count in items.items()]


def _with_gifts(events, gifts: Gifts, clock=time.time, *, keep_ticks=False):
    """Events with pickups held back in ``gifts`` and let out folded when due."""
    for event in events:
        yield from gifts.due(clock())
        if event is None:
            if keep_ticks:
                yield None
            continue
        if event.get("kind") in PICKUPS and not event.get("folded"):
            who = str(event.get("who") or "somebody")
            gifts.add(who, event.get("took") or [], clock(), event["kind"])
            continue
        yield event


class DeferredWake:
    """Coalesce own work notifications; read fresh state once the pause expires."""

    def __init__(self):
        self.pending = None

    def defer(self, event):
        if event.get("kind") in WAKING:
            self.pending = event

    def clear(self):
        self.pending = None

    def take(self, now, *, heard_at, woke_at, fled_at):
        if self.pending is None:
            return None
        if (now - heard_at < QUIET_AFTER_HIM or now - woke_at < WAKE_EVERY
                or calm_now(self.pending, fled_at, now)):
            return None
        event = self.pending
        self.clear()
        return event


def calm_now(event: dict, fled_at: float, now: float) -> bool:
    """A calm occasion while she is still running — held back, not said."""
    calm = event.get("kind") in CALM or (event.get("kind") == "progress" and "came_upon" in event)
    return calm and now - fled_at < DANGER_HOLD


def about_whom(event: dict) -> str:
    """Whom this occasion is about.

    Not "who spoke": a world note about a person is a turn about him too, though he was silent.
    And for a death the person lies in a field of its own, because "died" and "HE killed" are
    different events, and the second names him directly.
    """
    if event.get("kind") == "died":
        return str(event.get("by_player") or "")
    return str(event.get("who") or "")


def _note(event: dict) -> str:
    """A world note about a person nearby — in words, in square brackets.

    The brackets are not decoration: the player's own line arrives over this same channel, and
    a note must be distinguishable from someone's speech. The pack reads these lines as tags
    (`gift`, `watched`, `he_left`, `he_is_in_danger`), so FACTS are named here and no conclusions
    drawn: "he left", not "he abandoned you". What it means is her business.
    """
    kind = event.get("kind")
    who = event.get("who") or "somebody"
    if kind in PICKUPS:
        took = ", ".join(
            f"{one.get('what')}"
            + (f" x{one['count']}" if (one.get("count") or 1) > 1 else "")
            for one in event.get("took") or []
        )
        if kind == "picked_up_his":
            # Not a gift: he gave nothing. A fact of what she did with his things.
            return f"[{who} died; you picked up the things he dropped: {took or 'something'}]"
        return f"[{who} gave you {took or 'something'}]"
    if kind == "player_died":
        how = str(event.get("how") or "").strip()
        rule = " — this world is hardcore, a death here is final" if event.get("hardcore") else ""
        return f"[{who} died{f': {how}' if how else ''}{rule}]"
    if kind == "watched":
        at = "you work" if event.get("while_working") else "you"
        return f"[{who} has been standing there watching {at} for {event.get('watching_for', 0)}s]"
    if kind == "left":
        if event.get("why"):
            return f"[{who} {event['why']}]"
        return (
            f"[{who} walked off — {event.get('blocks')} blocks away,"
            f" gone {event.get('gone_for')}s]"
        )
    if kind == "noticed":
        kinds = ", ".join(
            str(k.get("what")) for k in event.get("kinds") or [] if k.get("what")
        )
        far = f"{event['distance']} blocks" if event.get("distance") else ""
        where = " ".join(x for x in (far, str(event.get("bearing") or "")) if x)
        what = event.get("what") or "something made"
        return (
            f"[you noticed far off: {what}"
            + (f" ({kinds})" if kinds else "")
            + (f", {where}" if where else "")
            + "]"
        )
    if kind == "remembered":
        again = f", {event['times']} times" if (event.get("times") or 1) > 1 else ""
        return (
            f"[you are back where this happened: {event.get('what') or 'something'}"
            f" — {event.get('ago') or 'a while ago'}{again}]"
        )
    if kind == "returned":
        return f"[{who} is back — {event.get('blocks')} blocks away]"
    if kind == "beside":
        them = ", ".join(
            f"{one.get('what')}"
            + (f" x{one['count']}" if (one.get("count") or 1) > 1 else "")
            for one in event.get("them") or []
        )
        return f"[{who} is standing with {them or 'somebody'}]"
    if kind == "died":
        # Killed by a person is different news from "died", and it is named directly.
        # What it means she decides; the wire only does not lose it.
        if event.get("by_player"):
            return f"[{event['by_player']} killed you]"
        how = event.get("how")
        return f"[you died — {how}]" if how else "[you died]"
    if kind == "at_risk":
        return f"[a {event.get('from')} is {event.get('blocks')} blocks from {who}]"
    if kind == "falling_behind":
        # A fact, not a conclusion: he is far away. What it means — catch up, drop the work or
        # tell him to stop — is her business, not the note's. Whether she was busy or simply
        # cannot keep up are different news, and the second must not be served as the first.
        where = f"[you are walking with {who} and he is {event.get('blocks')} blocks away"
        if event.get("busy"):
            # The work does not stop (11.09): the router no longer drops her business to catch
            # up. She will catch up when she finishes — unless she decides to drop it herself.
            return where + " — you are still at what you were doing; you will catch up after]"
        return where + " — you are following and not keeping up]"
    if kind == "lost_sight":
        return f"[you are walking with {who} and cannot see him from here]"
    if kind == "lost_them":
        if event.get("gone") is False:
            return (
                f"[{who} is {event.get('blocks')} blocks ahead — too far to catch,"
                " and you are still walking after him]"
            )
        return f"[{who} is gone from the world — you are walking with nobody now]"
    if kind == "advanced":
        # A fact and a time, without conclusions. What an advancement title means and whether
        # three advancements in an evening is fast is her business, not the note's.
        since = event.get("since")
        pace = f", {since}s after the last one" if isinstance(since, int) else ""
        return f"[{who} {VERB.get(event.get('tier'), VERB['task'])} \"{event.get('what')}\"{pace}]"
    if kind == "fled":
        hit = f"a {event.get('from')} hit you"
        if event.get("to") and event.get("to") != "away":
            return f"[{hit} — you are running to {event['to']}]"
        return f"[{hit} — you are running away, there is nobody to run to]"
    if kind == "cannot_reach":
        return (
            f"[you are walking with {who} and cannot get to him from where you"
            f" stand — {event.get('blocks')} blocks]"
        )
    return f"[{kind}]"


def _her_name(port: str) -> str:
    try:
        with urllib.request.urlopen(f"{port}/state?peek=1", timeout=5) as answer:
            return str((json.load(answer).get("her") or {}).get("name") or "")
    except OSError:
        return ""


def _world_id(port: str) -> str | None:
    """Which world she is in, as the router fingerprints it; None when it cannot say.

    Read every turn, not once: he can make a new world while she keeps running, and a
    pack's loop (engine/loop.py) steps on exactly that. A `peek` read: only her turn's
    own read of the state spends what the Router carries for a few turns (an example).
    """
    try:
        with urllib.request.urlopen(f"{port}/state?peek=1", timeout=5) as answer:
            world = (json.load(answer).get("world") or {}).get("id")
    except (OSError, ValueError):
        return None
    return str(world) if world else None


def visible(event: dict, unseen: frozenset[str]) -> bool:
    """Whether this character is told about the event at all (pack `unseen_notes`)."""
    return event.get("kind") not in unseen


def main() -> int:
    # A Windows console is cp1251 or cp866, and one arrow in a status line was enough
    # to kill her: she heard the player, answered in chat, took the goal, and the
    # process died PRINTING what she had done. A detail of display must never be able
    # to end the evening — the turn itself was already guarded, and the report was not.
    for stream in (sys.stdout, sys.stderr):
        try:
            # line_buffering, because a redirected stdout is block-buffered: five of her lines
            # sat in the buffer and would have arrived only on exit. A log visible only after
            # the process dies is not a log.
            stream.reconfigure(errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass  # not a real console; nothing to soften

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", default="", help="pack name; default CHARACTER from .env")
    parser.add_argument("--port", default="", help="router base URL; default GAME_PORT")
    args = parser.parse_args()

    service = get_service()
    if service.hands is None and not args.port:
        print("GAME_PORT is not set, so there is no world to sit in.")
        print("See docs/GAME_PORT.md.")
        return 1
    port = (args.port or service.hands.base).rstrip("/")
    args.character = args.character or load_settings().character
    if not args.character:
        print("CHARACTER is not set, so nobody is chosen to sit in the world.")
        print(f"Put CHARACTER=<pack> in .env; there is {', '.join(sorted(service.model_names()))}.")
        return 1

    if not service.has_model(args.character):
        known = ", ".join(sorted(service.model_names()))
        print(f"no character called {args.character!r}; there is {known}")
        return 1

    display = service.registry.get(args.character).meta.display_name
    # What she does not see at all is decided by the pack (a story game is not shown the game's mechanics).
    unseen = frozenset(service.registry.get(args.character).unseen_notes)
    in_world = _her_name(port)
    print(f"character {display}")
    print(f"in world  {in_world or '?'}")
    if in_world and in_world.lower() != display.lower():
        # Two products disagreeing quietly is worse than either being wrong.
        print(f"⚠ the world calls her {in_world}, but you are playing {display}.")
        print(f"  The router logs in under its own name: make run NAME={display}")
    if unseen:
        print(f"does not see {', '.join(sorted(unseen))}")
    print("listening to chat. Ctrl+C to quit.\n")

    # One window and one relationship PER PLAYER. Two people in the same world
    # are two conversations, and a shared window is how the answer to one of them
    # ends up carrying what the other said.
    windows: dict[str, list[ChatMessage]] = {}

    woke_at = 0.0
    heard_at = 0.0
    # WHOM the last turn was about. Not the same as "who spoke last": a world note about a
    # person is a turn about him too, though he was silent.
    last_person = ""
    gifts = Gifts()
    fled_at = 0.0
    deferred = DeferredWake()
    for event in _with_gifts(_ticking(_listen(port)), gifts, keep_ticks=True):
        if event is None:
            event = deferred.take(time.time(), heard_at=heard_at, woke_at=woke_at, fled_at=fled_at)
            if event is None:
                continue
        if not visible(event, unseen):
            continue
        kind = event.get("kind")

        # `came_upon` arrives as a turn note, not as an event kind of its own: in the stream it
        # is `progress` with that key. Ask what the event is, not its name — today that cost the
        # router a crash (R33).
        about_him = kind in WITH_CONTENT
        notable = about_him or kind in WAKING or (kind == "progress" and "came_upon" in event)

        if kind == "fled":
            fled_at = time.time()
        if notable and calm_now(event, fled_at, time.time()):
            deferred.defer(event)
            continue
        if notable:
            # The rate threshold is about her OWN business: attempts close every few seconds,
            # and without it that is chatter. Occasions about a person are few and already
            # thinned out by the router — about a gaze and danger it speaks no more than once a
            # minute per person — so muting them again means losing them.
            if not about_him and time.time() - woke_at < WAKE_EVERY:
                deferred.defer(event)
                continue
            # A conversation outranks her own occasion: the floor is taken in silence, not across
            # what was just said. Otherwise her own turn looks like "you're not listening to me"
            # exactly where he is listening to her.
            quiet = QUIET_AFTER_HIM if WITH_CONTENT.get(kind) is None else WITH_CONTENT[kind]
            if time.time() - heard_at < quiet:
                deferred.defer(event)
                continue
            woke_at = time.time()
            # Whose turn this is.
            #
            # Live 09.09: he killed her, and the record went into a conversation WITH HERSELF. The
            # `died` event has no `who` field — it has `by_player` — the loop had just restarted,
            # `last_person` was empty, and the fallback was HER OWN name. As a result a second ledger
            # appeared, `minecraft:Yukina`, where the −8 trust for the killing went: he killed her, and
            # it cost him nothing. And a turn later she did not remember it — the note lay in another window.
            #
            # There is no conversation with oneself, so there is no fallback with her name any more:
            # no person — no turn. Silence is more honest than a ledger that belongs to
            # nobody.
            who = about_whom(event) or last_person
            if not who:
                continue
            deferred.clear()  # This turn reads the current world, including pending outcomes.
            last_person = who
            window = windows.setdefault(who, [])
            # A turn about her work goes WITHOUT content, and that is not an omission: the world
            # state is assembled anew every turn, and it already holds the unfinished wish, what
            # waits for her at the furnace, and how the last attempt ended. She did not lack
            # information, she lacked a turn to speak.
            #
            # But an occasion about a person needs information: no state says that he JUST put a
            # diamond in her hands. That is a moment, not a state of affairs, and without content
            # only an empty bracket is left of it.
            said = _note(event) if about_him else f"[{kind}]"
            try:
                result = service.complete(
                    args.character,
                    [*window, ChatMessage(role="user", content=said)],
                    session_key=f"minecraft:{who}",
                    world=_world_id(port),
                )
            except Exception as why:  # noqa: BLE001
                print(f"[the turn failed: {why}]", file=sys.stderr)
                continue
            if getattr(result, "game_feedback_pending", False):
                deferred.defer({"kind": "waiting"})
            print(f"  {said}")
            if result.reply.strip():
                print(f"<{display}> {result.reply}")
                _say(port, result.reply)
            if result.did:
                print("  " + " · ".join(result.did))
            # A note about HIM and her answer are an exchange with him, and they belong in the
            # window: otherwise a turn later, at "do you like it?", she has nothing to remember
            # she had just thanked him with. A note about her own furnace is not an exchange and
            # still does not go into the window.
            if about_him:
                window.append(ChatMessage(role="user", content=said))
                window.append(ChatMessage(role="assistant", content=result.reply))
                windows[who] = window[-WINDOW:]
            continue

        if kind != "heard":
            continue
        who, said = event.get("who") or "somebody", (event.get("said") or "").strip()
        if not said:
            continue
        last_person = who
        deferred.clear()  # A human turn also receives the latest action outcome.
        # A mark that he spoke: her own occasion stays silent for this long afterwards.
        heard_at = time.time()
        print(f"<{who}> {said}")

        window = windows.setdefault(who, [])
        # What he handed her in the last seconds rides in the same turn, before his words:
        # one reaction to both, not a thank-you per pickup and then an answer.
        said_to_her = f"<{who}> {said}"
        for held in gifts.take(who):
            note = _note(held)
            said_to_her = f"{note}\n{said_to_her}"
            print(f"  {note}")
        # The speaker is NAMED to her.
        #
        # In a game chat you see who typed; she was seeing only the words. Live
        # 03.09 she asked the world to follow `"user"` — a placeholder, because
        # nothing had told her he was called HontoUKI — and the world correctly
        # answered that nobody by that name is here. The name is not decoration:
        # every verb about a person takes one.
        try:
            result = service.complete(
                args.character,
                [*window, ChatMessage(role="user", content=said_to_her)],
                session_key=f"minecraft:{who}",
                world=_world_id(port),
            )
        except Exception as why:  # noqa: BLE001 - one bad turn must not end the evening
            print(f"[the turn failed: {why}]", file=sys.stderr)
            continue

        if getattr(result, "game_feedback_pending", False):
            deferred.defer({"kind": "waiting"})

        window.append(ChatMessage(role="user", content=said_to_her))
        window.append(ChatMessage(role="assistant", content=result.reply))
        windows[who] = window[-WINDOW:]

        if result.reply.strip():
            print(f"<{display}> {result.reply}")
            _say(port, result.reply)
        if result.did:
            print(f"  → {' · '.join(result.did)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
