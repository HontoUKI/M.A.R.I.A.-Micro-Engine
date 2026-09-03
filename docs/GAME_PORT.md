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

She acts by ending her reply with lines of her own:

```
Alright, hold on.
DO: gather {"object": "oak_log", "quantity": 8}
DO: build {"object": "shelter", "where": {"x": -45, "y": 64, "z": -43}}
REPEAT: 2
```

The engine cuts those lines out before the reply is returned, so a decision is
never read aloud as speech, and hands them to the router: one step once is an
attempt, anything else is a plan. `REPEAT` repeats the whole list, because "do
that twenty times" is a sequence even when the sequence has one step in it.

`DO:` counts only at the start of a line. Any other rule would turn a
character's own *"just do: whatever you like"* into an order to her body, and
no test in which she is obedient would ever show it.

Every response reports what she set going in `x_micro_engine.did`, so a client
can show that the words and the world agreed.

## Did it work

`POST /v0/attempts` returns while the attempt is still **running** — a verb
takes as long as it takes, and a call that waited for it would make her
uninterruptible for minutes. So the answer arrives on the *next* turn, in
words, as "the last thing you tried". Without that she would learn of the
world's refusal from nowhere, which is how a character ends up cheerfully
reporting a house she never built.
