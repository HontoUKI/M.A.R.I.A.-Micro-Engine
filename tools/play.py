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

    python tools/play.py --character yukina
    make play CHARACTER=yukina

The router is not started here, for the reason it is not started anywhere: it
attaches to a world somebody is already running.
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.contracts import ChatMessage  # noqa: E402
from app.deps import get_service  # noqa: E402

# How much of a conversation she carries between lines. Small on purpose: chat
# lines are short, and a window measured in messages rather than tokens is the
# honest unit for a place where people type "k".
WINDOW = 8

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
            print(f"[не сказала: {why}]", file=sys.stderr)


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
    while True:
        try:
            with urllib.request.urlopen(f"{port}/events", timeout=None) as stream:
                for raw in stream:
                    line = raw.decode("utf-8", "replace").strip()
                    if not line.startswith("data:"):
                        continue
                    try:
                        yield json.loads(line[5:].strip())
                    except ValueError:
                        continue
        except (OSError, urllib.error.URLError) as why:
            print(f"[связь с роутером потеряна: {why}]", file=sys.stderr)
            return


def _her_name(port: str) -> str:
    try:
        with urllib.request.urlopen(f"{port}/state", timeout=5) as answer:
            return str((json.load(answer).get("her") or {}).get("name") or "")
    except OSError:
        return ""


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--character", required=True, help="pack name, e.g. yukina")
    parser.add_argument("--port", default="", help="router base URL; default GAME_PORT")
    args = parser.parse_args()

    service = get_service()
    if service.hands is None and not args.port:
        print("GAME_PORT is not set, so there is no world to sit in.")
        print("See docs/GAME_PORT.md.")
        return 1
    port = (args.port or service.hands.base).rstrip("/")

    if not service.has_model(args.character):
        known = ", ".join(sorted(service.model_names()))
        print(f"no character called {args.character!r}; there is {known}")
        return 1

    display = service.registry.get(args.character).meta.display_name
    in_world = _her_name(port)
    print(f"персонаж {display}")
    print(f"в мире   {in_world or '?'}")
    if in_world and in_world.lower() != display.lower():
        # Two products disagreeing quietly is worse than either being wrong.
        print(f"⚠ мир зовёт её {in_world}, а играешь ты {display}.")
        print(f"  Роутер логинится под своим именем: make run NAME={display}")
    print("слушаю чат. Ctrl+C — выйти.\n")

    # One window and one relationship PER PLAYER. Two people in the same world
    # are two conversations, and a shared window is how the answer to one of them
    # ends up carrying what the other said.
    windows: dict[str, list[ChatMessage]] = {}

    for event in _listen(port):
        if event.get("kind") != "heard":
            continue
        who, said = event.get("who") or "somebody", (event.get("said") or "").strip()
        if not said:
            continue
        print(f"<{who}> {said}")

        window = windows.setdefault(who, [])
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
                [*window, ChatMessage(role="user", content=f"<{who}> {said}")],
                session_key=f"minecraft:{who}",
            )
        except Exception as why:  # noqa: BLE001 - one bad turn must not end the evening
            print(f"[ход не вышел: {why}]", file=sys.stderr)
            continue

        window.append(ChatMessage(role="user", content=f"<{who}> {said}"))
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
