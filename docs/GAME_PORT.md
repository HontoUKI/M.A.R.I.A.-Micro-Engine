# The game port

## Окно модели и бюджет

В игровом режиме Ollama требуется `NUM_CTX >= 16384`; без явного значения движок
запрашивает 16384. На старте журнал печатает запрошенное окно и потолок промпта.
Это настройка запроса, а не утверждение о фактическом лимите облачного провайдера.
`PROMPT_MAX_TOKENS` оставляет место для ответа; обычный ход целится в 6–8K.
Бюджет сначала резервирует последние реплики разговора, затем выделяет место миру.
Мир сокращается целыми секциями, обрезка отмечается в промпте.

A character in this engine answers messages. With a **game port** attached she
can also act — walk somewhere, pick something up, build a house — in a world
running in another process.

The engine does not contain a game, and it never will. It speaks a small
published HTTP protocol to a **router**: a separate program that owns one game
and answers three questions.

| The question | The route |
|---|---|
| What do I see? | `GET /v0/state` |
| What can I do here? | `GET /v0/affordances` |
| Did it work? | `GET /v0/attempts` |

Acting is `POST /v0/attempts` for one goal and `POST /v0/plans` for several in
order. The reference router is
[M.A.R.I.A.-Minecraft-Router](https://github.com/HontoUKI/M.A.R.I.A.-Minecraft-Router);
anything that answers those routes will do.

## Turning it on

```bash
GAME_PORT=http://127.0.0.1:25580/v0
```

That is the whole configuration. Empty means there is no game and no character
is told there is one.

## Two boundaries, and why they are worth the inconvenience

**A pack cannot turn this on.** Whether a game is attached is a deployment
decision, exactly like the choice of model. A character pack stays what the
spec says it is — prompt text and numbers — so no published character can reach
the network because somebody wrote a clever YAML file. The flip side is that
*any* character can act once a world is attached: having hands is a property of
where she is running, not of who she is.

**The vocabulary belongs to the game.** The router declares its own verbs and
what each of them needs; the engine types none of them and passes a goal's
`where` through as opaque JSON. That is what lets a second game be attached
without a line changing in here — and it is why the block she reads is
assembled from names the game sent rather than from anything written in this
repository.

The framing around those names *is* the engine's: how to choose, what form an
answer takes, and that wanting none of it is an answer. Text arriving from
another process and landing in a prompt as instructions is a channel for
putting words in somebody's head, and it stays closed by construction rather
than by trusting whoever wrote the adapter.

## What she sees, and what she says back

Once a turn, the dynamic tail carries the world: where she is, what she can do
and what each verb needs, and what became of the last thing she tried. It is in
the *tail* and not the pinned prefix on purpose — a world pinned once is a
description of where she used to be.

She acts by ending her reply with a block of her own:

```
Alright, hold on.
<play>
repeat 2 {
  gather(oak_log, 8)
  build(shelter, at: (-45, 64, -43))
}
</play>
```

The language inside the block belongs to the **game**, not to the engine
(28.09). The engine cuts the block out before the reply is returned, so a
decision is never read aloud as speech, and sends its text as it is to the
router's `POST /v0/read`. What comes back is what `/attempts` and `/plans`
already take — steps, how many times through, and a word (`continue` / `drop`)
about the attempt she was pulled off. One step once is an attempt, anything else
is a plan. The router's grammar — calls, `ALL`/`FIRST` selections, places — is
described in its `minecraft/docs/play.md`; this side types none of it.

Reading is all the router does with it. Pack bounds and the choice between going
back and starting something new stay here, where her state is: a selection
names no things, so a bound treats it as "everything" unless she left the
forbidden thing out with `EXCEPT`. A block the router cannot read comes back
with its line, column and reason, and she is told it next turn.

The model writes routines as Router DSL: `@teach(details: "purpose") def name(...) { calls }`.
The engine forwards source to `/read`; the Router validates the entire block and
returns syntax locations and source fragments. Saving requires `routine_saved`,
`saved: true`, name and version. Launch it on a separate turn with
`run(name, parameter: value)`. JSON remains the compiled HTTP/storage format;
models do not write JSON steps. Read `lookup Teach` for the Router's grammar.

The block exists because a line form did not survive the trip. Replies are cut
into sentences for delivery, and whatever does that joins neighbouring lines
with a space. Inside `<play>` the text survives being cut up, and an
**unclosed** block swallows everything to the end of the reply: an unfinished
decision is better lost than spoken aloud, which is exactly what happened on
03.09 when she answered a player with the literal words "DO: gather ...".

The old `DO:` form is gone. A line of it outside the block (or a bare
`REPEAT:`, `CONTINUE`, `DROP`) is still cut from the speech and she is told it
was not read — only at the start of a line, so a character's own *"just do:
whatever you like"* stays speech.

Every response reports requests she set going in `x_micro_engine.did`. This is
delivery evidence, not proof that their effects completed.

## Router refusals and action results

Explicit HTTP 4xx/action refusals retain the Router's diagnostic body and become
next-turn feedback. A refused action, resume or abandon is not reported in did.
Reader refusals remain source diagnostics; no action was sent from that block.

HTTP 202 can return an action that already closed as foreclosed or abandoned.
That record is reported as an action outcome, separately from a rejected request.
Its reason and confirmation remain available; an unconfirmed effect must not be
treated as proof that nothing happened or as permission to spend resources again.

A release is the exception. `abandon` is answered with the record it just closed,
and a plan keeps the outcome it had already recorded, so a closed record is what a
successful `drop` looks like. Only an explicit refusal stops a release; otherwise
the rest of the drop — the plan, then any replacement steps — goes out as usual.

HTTP 5xx or a lost response leaves delivery uncertain. The model is told to inspect
current state and recent attempts before repeating. This consumer port recognizes
generic Router result fields and introduces no Minecraft verbs or DSL parser.

## What she has on

When the router sends `state.equipment`, it opens the world block. It is one short block: each slot, what is in it, and what she carries that fits it ("head: iron_helmet. Can equip: diamond_helmet"). Accessory slots are included, as are her healing item and her tracked ammunition.

Below it stay only the ammunition changes of the last five turns, because the stock is already in the block. The `wearing` list in her situation is dropped then, so the same armour is not said twice.

With an older router nothing changes: the ammunition block shows the stock as before.

## Did it work

`POST /v0/attempts` returns while the attempt is still **running** — a verb
takes as long as it takes, and a call that waited for it would make her
uninterruptible for minutes. So the answer arrives on the *next* turn, in
words, as "the last thing you tried". Without that she would learn of the
world's refusal from nowhere, which is how a character ends up cheerfully
reporting a house she never built.

## What the world says on its own

A world does not wait to be asked. The router streams what happened — an attempt
closing, a furnace that now works without her, somebody walking up — and
`tools/play.py` gives her the floor for it, passing the occasion as a note in
square brackets on the same channel a player's line arrives on.

| note | when |
|---|---|
| `[closed]` · `[waiting]` · `[interrupted]` | something of HERS ended, stalled, or was cut off |
| `[HontoUKI gave you diamond x2]` | he handed her things and she picked them up |
| `[HontoUKI has been standing there watching you work for 7s]` | he came over and stayed |
| `[HontoUKI walked off — 63 blocks away, gone 31s]` · `[HontoUKI is back — 9 blocks away]` | he left, he returned |
| `[a creeper is 2 blocks from HontoUKI]` | something can hurt him right now |
| `[HontoUKI died: HontoUKI was slain by Ghost — this world is hardcore, a death here is final]` | the game announced his death; everyone in the world hears it |

Two rules hold this together, and both are about not deciding for her.

**A note states a fact and never a reading.** "He walked off", never "he
abandoned you". What an absence means — missing him, relief, nothing at all —
belongs to the character, and a pack is free to have no opinion about it. The
same boundary the router keeps with a player's words, which it carries and does
not interpret.

**Her own work arrives without content, and a note about a person carries it.**
The state is rebuilt every turn, so "the attempt closed" needs no detail: what
she was doing is already in front of her. Nothing anywhere says he *just* put a
diamond in her hands — that is a moment, not a state of affairs, and without its
content it would reach her as an empty bracket.

**Pickups are gathered, not announced one by one.** A gift is held for
`GIFTS_LIVE` seconds (10) and counted by item. If he speaks in that time, the
whole list rides in front of his line in the same turn — one reaction to both.
If he stays quiet, it goes out once, as a single note. Live, on 30.09, she
picked up his things after he died, one spot after another, and thanked him
five times in thirty seconds.

**What he dropped when he died is not a gift.** The router tells them apart by
the time of his death (`picked_up_his`), and the note says so:
`[HontoUKI died; you picked up the things he dropped: …]`. The same queue holds
it, never mixed into a gift.

**Every turn says which world it happens in.** `tools/play.py` reads the
router's `state.world.id` (a hash of the world's seed) and passes it to the
turn. A pack with a `loop` (spec §2.14) steps on a new world; for every other
pack it changes nothing.
That read, like the one for her name, is a `GET /state?peek=1`: only the turn's own
read of the state counts as her turn, which is what spends the three turns the
router carries a selected routine example for.

**Calm notes wait while she runs.** For `DANGER_HOLD` seconds (20) after she
flees, "noticed far off", "you are back where…", "he is watching" and her own
work stay unsaid. The chase, a hit and death always get through. Live on 30.09,
a ghost was chasing her, and one of her two cries for help was spent on
"a structure, 11 blocks north-east".

A pack that wants to react to any of this says so in its tags; `characters/yukina`
is the worked example, including the trap that comes with it — a strong `neglect`
tag reads `[closed]` as the player ignoring her unless the pack gives the world
its own tag.

## Справочник по запросу — 01.10

С 02.10 имя известной рутины также является статьёй `lookup`: параметры и пример
вызова берутся из её текущего определения, включая выученные рутины. Незнакомый
параметр запуска вызывает отказ с допустимыми именами до замены текущей работы.

Короткие завершения собственных действий больше не теряются в паузе речи:
игровой цикл хранит один последний повод `closed` / `waiting` / `interrupted` и
доставляет его после ограничений частоты, разговора и опасности. Ход заново читает
состояние мира. Любой другой доставленный ход, уже прочитавший исход, снимает
ожидание; старые результаты не воспроизводятся отдельной очередью реплик.

Непрочитанный вызов тоже оставляет один повод `waiting`: для него роутер не создаёт
попытку и не пришлёт `closed`. Следующий ход получает причину ошибки с теми же
ограничениями частоты и паузами. Пустой `<play>` и реплика без `<play>` означают
допустимое бездействие и сами нового хода не создают. Повторный lookup в окончательном
ответе не исполняется, но его потеря явно сообщается на следующем ходе; исполнение
остальных вызовов этого ответа не отменяется. При защите запрет справки не создаёт
дополнительный повод для повторного запроса. Внутренний флаг
`TurnResult.game_feedback_pending` используется игровым циклом и не добавлен в HTTP-ответ.
Непроизнесённые ошибки разбора, отправки и ограничения пака хранятся отдельно для
пары сессия/персонаж: новый исполнитель запроса получает их до построения промпта.
Они стоят перед обзором мира, чтобы объём окружения не вытеснил причину отказа.
Успешный следующий ход снимает уведомление; сбой модели сохраняет его для повтора.
Сброс отношений очищает эти уведомления. Перезапуск процесса их не сохраняет на диск.

Если читатель игры не ответил, команды не отправлены на исполнение. Если связь
оборвалась при отправке действия, его принятие неизвестно: движок предлагает проверить
состояние и историю до повтора. Это отдельное уведомление после восстановления связи,
а не утверждение, что мир отказал или ничего не произошло.

Роутер с флагом `glossary` отдаёт короткий блок мира вместо подсказок всех действий.
Каждый ход сохраняет ситуацию, предмет в руке, сумку, отказы и список всех рутин
`{name, details}`. При нехватке бюджета разговор получает резерв первым; список рутин
сохраняется даже при отсечении больших разделов окружения.

`<lookup>Teach</lookup>` читает статью через `GET /v0/glossary?name=Teach`, после чего
движок повторно вызывает модель внутри того же хода. Действия из первого ответа
не выполняются. Второй lookup не обрабатывается, теги не выходят в речь. При угрозе
справка выключена без дополнительного вызова модели; её боевые действия остаются доступны.
Неизвестное имя и `Glossary` дают оглавление только на текущий ход.

У разговора три ячейки справки. Статья со спутниками занимает одну ячейку, живёт десять
её ходов от последнего чтения; повторное чтение продлевает срок, новая статья вытесняет
самую давно прочитанную. Ячейки разделены по сессии и персонажу; сброс отношений очищает
их. В блоке напечатаны возраст и оставшийся срок. Успешные вызовы роутера показываются
как `<play>`; для сохранения последней успешно выполненной **рутины** есть `teach`
без тела. Одиночный вызов можно поместить в тело `teach { вызов }`, затем добавить
`name(...)` и `details(...)`. Тело не записывается моделью как JSON steps.
