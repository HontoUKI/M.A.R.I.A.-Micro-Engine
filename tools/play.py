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
import time
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

# Сколько ждать перед новой попыткой подключиться к потоку. Секунды, не мгновение:
# роутер перезапускают руками, и частить в закрытый порт — это шум, а не готовность.
RECONNECT_EVERY = 3.0

# События, на которые ей стоит дать ход.
#
# Долгая работа не даёт ей хода вовсе: шахта говорит «попалась железная руда», а
# следующий раз её спросят, когда шахта кончится. Всё, что автор перечислял как
# «правильный выбор» — вскопать жилу, осветить пещеру, зачистить подземелье, — упирается
# не в отсутствие суждения, а в отсутствие МОМЕНТА, когда его можно высказать.
#
# Список короткий и структурный, а не по вкусу: работа кончилась · работа пошла сама и
# тело свободно · её сбили · и то, что она встретила по дороге. Ошибиться тут дёшево —
# игрок рядом и поправит; дорого спамить, поэтому есть порог.
WAKING = ("closed", "waiting", "interrupted")

# И то, что сделал ЧЕЛОВЕК рядом.
#
# Про него до сих пор существовало ровно одно событие — он заговорил, — и всё остальное,
# чем человек присутствует, до неё не доезжало. Он подошёл и смотрит, как она строит; он
# положил ей в руки алмаз; он ушёл за холм; за его спиной крипер. Персонаж, у которого
# всё это есть в тегах, без этого провода не может выбрать их ни разу: механизм построен
# и до момента не доезжает — та самая повторяющаяся форма.
#
# Число — сколько секунд тишины после ЕГО реплики нужно этому поводу. Ноль почти у всех,
# и это не небрежность: `QUIET_AFTER_HIM` защищает от того, чтобы её собственное дело
# перебило разговор, а здесь повод — сам разговор и есть, только не словами. Ответить
# на подаренный алмаз через секунду после «take this» — не перебить его, а услышать.
#
# Исключение — взгляд: он может стоять и смотреть посреди беседы, и «ты на меня
# смотришь!» поверх его же реплики это ровно прежний дефект.
ABOUT_HIM = {
    "given": 0.0,
    "at_risk": 0.0,
    "left": 0.0,
    "returned": 0.0,
    "beside": 0.0,
    "watched": None,  # None — держать общий порог тишины
}

# Не чаще раза в столько секунд. Ход, который нельзя перебить и который идёт каждые две
# секунды, — это уже не внимание, а трескотня.
WAKE_EVERY = 20.0

# И не раньше, чем столько секунд после ЕГО реплики.
#
# Живьём 08.09, из её же расшифровки: он написал «take some cooked cod», она ответила в
# 19:35:00 — и в 19:35:02 взяла слово сама, потому что попытка закрылась. Пауза между её
# ответом и её же «Hellooo? Are you even listening to me?» — ДВЕ СЕКУНДЫ.
#
# Порог у очереди говорить был только один и не тот: «не чаще раза в двадцать секунд»
# считает от прошлого её хода и ничего не знает про то, что он сказал только что. Пока
# она стояла в тупике `gather → craft → gather`, попытки закрывались каждые несколько
# секунд, и каждая давала ей слово поверх разговора.
QUIET_AFTER_HIM = 45.0

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
            # Возвращаться, а не выходить: докстринг обещал это с самого начала, а код
            # делал обратное — живьём 03.09 перезапуск роутера убил её насмерть, и она
            # молчала в мире, где игрок продолжал ей писать. Роутер это отдельный
            # процесс; его перезапуск не событие в её жизни.
            if not quiet:
                print(f"[связь с роутером потеряна: {why} — жду]", file=sys.stderr)
            quiet = True
            time.sleep(RECONNECT_EVERY)
            continue
        # Поток кончился без ошибки: тоже обрыв, просто вежливый.
        if not quiet:
            print("[поток кончился — жду]", file=sys.stderr)
        quiet = True
        time.sleep(RECONNECT_EVERY)


def _note(event: dict) -> str:
    """Записка мира про человека рядом — словами, в квадратных скобках.

    Скобки не украшение: по этому же каналу приезжает её собственная реплика игрока, и
    записка обязана быть отличима от чужой речи. Пак читает эти строки тегами (`gift`,
    `watched`, `he_left`, `he_is_in_danger`), поэтому здесь называются ФАКТЫ и не
    делается выводов: «он ушёл», а не «он тебя бросил». Что это значит — её дело.
    """
    kind = event.get("kind")
    who = event.get("who") or "somebody"
    if kind == "given":
        took = ", ".join(
            f"{one.get('what')}"
            + (f" x{one['count']}" if (one.get("count") or 1) > 1 else "")
            for one in event.get("took") or []
        )
        return f"[{who} gave you {took or 'something'}]"
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
    if kind == "returned":
        return f"[{who} is back — {event.get('blocks')} blocks away]"
    if kind == "beside":
        them = ", ".join(
            f"{one.get('what')}"
            + (f" x{one['count']}" if (one.get("count") or 1) > 1 else "")
            for one in event.get("them") or []
        )
        return f"[{who} is standing with {them or 'somebody'}]"
    if kind == "at_risk":
        return f"[a {event.get('from')} is {event.get('blocks')} blocks from {who}]"
    return f"[{kind}]"


def _her_name(port: str) -> str:
    try:
        with urllib.request.urlopen(f"{port}/state", timeout=5) as answer:
            return str((json.load(answer).get("her") or {}).get("name") or "")
    except OSError:
        return ""


def main() -> int:
    # A Windows console is cp1251 or cp866, and one arrow in a status line was enough
    # to kill her: she heard the player, answered in chat, took the goal, and the
    # process died PRINTING what she had done. A detail of display must never be able
    # to end the evening — the turn itself was already guarded, and the report was not.
    for stream in (sys.stdout, sys.stderr):
        try:
            # line_buffering, потому что перенаправленный stdout блочный: пять её
            # реплик просидели в буфере и дошли бы только на выходе. Лог, который
            # виден лишь после смерти процесса, — это не лог.
            stream.reconfigure(errors="replace", line_buffering=True)
        except (AttributeError, ValueError):
            pass  # not a real console; nothing to soften

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

    woke_at = 0.0
    heard_at = 0.0
    last_speaker = ""
    for event in _listen(port):
        kind = event.get("kind")

        # `came_upon` приезжает заметкой хода, а не своим родом события: в потоке это
        # `progress` с этим ключом. Спрашивать надо у того, чем событие является, а не у
        # его имени — сегодня это стоило роутеру падения (R33).
        about_him = kind in ABOUT_HIM
        notable = about_him or kind in WAKING or (kind == "progress" and "came_upon" in event)

        if notable:
            # Порог частоты — про её СОБСТВЕННЫЕ дела: попытки закрываются каждые
            # несколько секунд, и без него это трескотня. Поводы про человека наперечёт
            # и уже прорежены роутером — про взгляд и про опасность он говорит не чаще
            # раза в минуту на человека, — так что глушить их ещё раз значит терять их.
            if not about_him and time.time() - woke_at < WAKE_EVERY:
                continue
            # Разговор старше собственного повода: слово берут в тишине, а не поперёк
            # только что сказанного. Иначе её собственный ход выглядит как «ты меня не
            # слушаешь» ровно там, где он её слушает.
            quiet = QUIET_AFTER_HIM if ABOUT_HIM.get(kind) is None else ABOUT_HIM[kind]
            if time.time() - heard_at < quiet:
                continue
            woke_at = time.time()
            who = event.get("who") or last_speaker or display
            window = windows.setdefault(who, [])
            # Ход про её работу идёт БЕЗ содержания, и это не упущение: состояние мира
            # собирается заново каждый ход, и в нём уже есть и незаконченное желание, и
            # то, что ждёт её у печи, и чем кончилась последняя попытка. Ей не хватало
            # не сведений, а очереди говорить.
            #
            # А поводу про человека сведения нужны: ни в каком состоянии не написано,
            # что он ТОЛЬКО ЧТО вложил ей в руки алмаз. Это момент, а не положение дел,
            # и без содержания от него остаётся пустая скобка.
            said = _note(event) if about_him else f"[{kind}]"
            try:
                result = service.complete(
                    args.character,
                    [*window, ChatMessage(role="user", content=said)],
                    session_key=f"minecraft:{who}",
                )
            except Exception as why:  # noqa: BLE001
                print(f"[ход не вышел: {why}]", file=sys.stderr)
                continue
            print(f"  {said}")
            if result.reply.strip():
                print(f"<{display}> {result.reply}")
                _say(port, result.reply)
            if result.did:
                print("  " + " · ".join(result.did))
            # Записка про НЕГО и её ответ — это обмен с ним, и в окне ему место: иначе
            # на «нравится?» через ход ей нечем вспомнить, что она только что
            # благодарила. Записка про её собственную печь обменом не является и в окно
            # по-прежнему не идёт.
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
        last_speaker = who
        # Отметка о том, что он говорил: её собственный повод молчит столько-то после.
        heard_at = time.time()
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
