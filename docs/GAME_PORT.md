# The game port

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

## Model window and budget

In game mode Ollama needs `NUM_CTX >= 16384`; without an explicit value the engine asks
for 16384. At startup the log prints the requested window and the prompt ceiling. This
is a request setting, not a claim about the cloud provider's actual limit.
`PROMPT_MAX_TOKENS` leaves room for the answer; an ordinary turn aims at 6–8K. The budget
first reserves the latest lines of the conversation, then gives the world its room. The
world is shortened by whole sections, and the cut is marked in the prompt.

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

## Reference on request — 01.10

Since 02.10 the name of a known routine is also a `lookup` article: its parameters and a
sample call come from its current definition, learned routines included. An unknown run
parameter is refused with the allowed names before the current work is replaced.

Short completions of her own actions are no longer lost in a pause of speech: the game
loop keeps one latest `closed` / `waiting` / `interrupted` occasion and delivers it after
the rate, conversation and danger limits. The turn reads the world state afresh. Any
other delivered turn that has already read the outcome clears the wait; old results are
not replayed as a separate queue of lines.

A call that could not be read also leaves one `waiting` occasion: the router creates no
attempt for it and will send no `closed`. The next turn gets the error's cause under the
same rate limits and pauses. An empty `<play>` and a line without `<play>` mean
legitimate inaction and create no new turn by themselves. A repeated lookup in a final
answer is not executed, but its loss is reported on the next turn; the other calls in
that answer still run. While defending, the reference ban creates no extra occasion for
asking again. The internal flag `TurnResult.game_feedback_pending` is used by the game
loop and is not part of the HTTP response. Unspoken parse, send and pack-limit errors
are kept separately per session/character pair: a new request runner gets them before
the prompt is built. They stand before the world overview, so the volume of the
surroundings cannot push the cause of a refusal out. A successful next turn clears the
notice; a model failure keeps it for the retry. A relationship reset clears these
notices. A process restart does not keep them on disk.

If the game reader did not answer, the commands were not sent for execution. If the
connection broke while an action was being sent, whether it was accepted is unknown:
the engine suggests checking the state and the history before retrying. This is a
separate notice after the connection comes back, not a claim that the world refused or
that nothing happened.

A router with the `glossary` flag hands over a short world block instead of hints for
every action. Every turn keeps the situation, the item in hand, the bag, refusals and the
list of all routines `{name, details}`. When the budget runs short the conversation gets
its reserve first; the routine list is kept even when large sections of the surroundings
are cut.

`<lookup>Teach</lookup>` reads the article through `GET /v0/glossary?name=Teach`, after
which the engine calls the model again within the same turn. Actions from the first
answer are not executed. A second lookup is not processed, and the tags do not leak into
speech. Under a threat the reference is switched off without an extra model call; her
fighting actions stay available. An unknown name and `Glossary` give the table of
contents for the current turn only.

A conversation has three reference slots. An article with its companions takes one slot
and lives ten of her turns from the last reading; reading it again extends the term, a
new article displaces the one read longest ago. The slots are separate per session and
character; a relationship reset clears them. The block prints the age and the remaining
term. Successful router calls are shown as `<play>`; to save the last successfully run
**routine** there is `teach` without a body. A single call can be put into the body of
`teach { call }`, then `name(...)` and `details(...)` added. The model does not write the
body as JSON steps.

## Game feedback

DSL errors reach the next turn with their position in the source.
`run(name, param: value)` calls a routine; primitives are called directly.
`<play>drop</play>` cancels the current paused attempt and the saved unfinished plan;
new calls may follow in the same block after the cancel. The code keeps the closed
plan's original refusal in the history. Sending an action does not confirm that the
request was carried out: the model has to match the state that follows against what
the player asked for — a successful craft does not mean the item was placed or handed
over.

## The five-turn action history

The router's `state.actions` carries measured item changes with a reason, a target,
an actor and an outcome. A craft and a placement are kept apart from later failed
retries. For example: `-4 oak_planks, reason: craft`, `+1 crafting_table, reason:
craft`, then `-1 crafting_table, reason: placed`. Consumption by the reflex has
`actor: reflex` and `reason: healing_reflex`. The player receiving a thrown item is
confirmed separately.

Confirmation is kept apart from the outcome: `packet_sent` means the packet was handed
to the transport, `server_ack` a matched answer with `acceptance:
accepted|rejected|unknown`, `effect_confirmed` an observed fact. `completion_basis`
says on which of these grounds an attempt ended. Without a confirmed effect the
history says `effect: unconfirmed` outright; neither sending nor an answer turns into
a game result. The stages of one attempt are refined through its revisions. Older
records without confirmations still read.

Every new revision is shown in the current turn and the next four; on the sixth it
disappears. Classification, a lookup continuation and world polls are not extra turns.
The history is kept in the session, although a new runtime is built for every request,
and it is cleared when the session resets or the router's stream changes. The old
formatters for the last attempt, refusal lists and successful calls are gone.

Priority ammunition is set through the DSL: `track(spectral_arrow, as: ammunition)`.
Exact modded IDs work without separate adapters. `enabled: false` removes the choice.
At the start of the `<body>` data the current count (zero included) and the measured
changes over five turns, with actor and reason, are printed. The changes are not
repeated below; removing the choice returns the facts still alive to the ordinary
history. This is an observation, not a reserve and not a weapon choice. For 1.20.1
Potion NBT one variant is supported: `track(potion, potion: fire_resistance)`.
Arbitrary CustomPotionEffects are not decoded.

The Ammunition block holds the consumables the agent chose, not only projectiles.
Current effects with their duration are printed next to it. `lock(item)` or
`lock(potion, potion: fire_resistance)` forbids consuming, right-clicking and reflex
healing with it until an explicit unlock. Automatic routines cannot lift it; an
ordinary preparation routine run on an order can. The count and the lock do not expire
with the five turns of history. The router does not guarantee the lock against unknown
use of other slots by modded packets or against server-side automatic activations.

### The routine wrapper — 03.10

The new source form: `@teach(details: "purpose") def my_routine(item: bread)
{ consume($item) }`. The name and parameters belong to `def`; a required parameter is
marked `null`. This is the DSL, not Python. The declaration is sent as a turn of its
own. The router checks it whole before saving, without running the body.
`routine_rejected` means `saved: false`; the model fixes the source by the line and
`block_path`. Only `routine_saved` with `saved: true`, a name and a version confirms
the save. Running it is the next turn. The confirmation comes in the shared action
history; no separate success channel for learning is needed.

### Source readiness — 12.10

`POST /v0/read` can additionally return `ready: false` and
`unresolved_calls: [{name, step_path, reason}]`. `step_path` is an opaque source
location, such as `steps[0].where.routine.steps[0]`; this consumer does not parse it.
`missing_routine` means the named routine was unknown at reading time;
`requires_binding` means the routine name needs parameter binding.

This is valid source with a readiness diagnostic, not a syntax rejection.
Forward declarations may still be saved, and returned steps still go through the
ordinary submission and pack-bound checks. Readiness does not confirm a save or
an action outcome. Check `routine_saved`, `saved: true`, name/version and the
action history for those results; re-read the source after defining or binding
the calls to check its current readiness. Older Router responses without this
metadata behave as before; `ready: true` leaves no readiness notice.

The diagnostic reaches the next real turn through a separate readiness notice,
including when there is no Router event to wake the game loop. It never goes
through the unread-source notice that says nothing moved. The notice is kept
across request runners per session/character, survives a failed model turn and
world-budget trimming, and is consumed once by a successful turn. Relationship
reset clears it; process restart does not persist it. No new field is added to
the public chat response or the character-pack schema.
