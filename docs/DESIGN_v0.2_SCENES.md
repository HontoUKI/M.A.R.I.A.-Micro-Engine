# Design — v0.2: multi-actor scenes and the narrator

> **Status: design, not implemented.** This documents the intended shape of the
> v0.2 Actor Model so the interfaces are agreed before code. It builds strictly
> on the v0.1 primitives (character packs, per-character state, the two-segment
> KV-cached prompt, and the moment-tag classifier) — nothing here throws those
> away; it generalizes them from *one* actor to *several* on a shared stage.

## Where this comes from

v0.1 is a **one-actor Actor Model**: a scene projects onto exactly one character
who answers the user. That is the whole engine — a single pack, a single state,
a single pinned identity prefix.

The idea for v0.2 came from two places meeting:

- **The engine's own shape.** Because each character is a *stable pinned prefix*
  (KV-cache friendly) plus a *cheap dynamic tail*, a second character is just a
  second pinned prefix. The machinery to hold more than one actor is already
  latent in the prompt layout.
- **The narrator** that emerged in the full M.A.R.I.A. runtime (ADR-0008): a
  *suffleur* who feeds a scene description and whom the character reacts to
  **as an event, never as a conversation partner**. That separates three roles
  that v0.1 collapses into "the user": who *delivered* a line, who *owns* it,
  and who it is *about*.

Put together, the engine stops being a chatbot with a costume and becomes a
small **stage**: a director, a cast of actors, a narrator, and a backdrop. This
is deliberately in line with the old rebirth branch's philosophy — the character
is not a service that answers; it is a presence that *acts within a scene*.

## The four new capabilities

### 1. More than one character in a dialogue

A **Scene** holds N loaded packs at once. Each actor keeps its **own**
everything it has today — its own `StateKernel` (affection/trust/bond toward the
subject), its own pinned identity prefix, its own memory namespace. A scene is a
thin object over the existing pieces:

```
Scene
  actors:   { "megumin": ActorState, "kaguya": ActorState, ... }
  narrator: NarratorState        # the suffleur channel (capability 2)
  backdrop: BackgroundContext     # the pinned scene image description (capability 3)
  director: DirectorMode          # who picks the next speaker (capability 4)
```

`ActorState` is exactly today's per-session bundle (pack + kernel + memory),
just keyed by `(scene_id, actor_id)` instead of `(session, pack)`. No new state
math — relationship axes still move only from the per-tag delta table, per actor.

### 2. Autonomous dialogue between actors — user as suffleur

Actors can talk **to each other**, not only to the user. A turn is no longer
"user says X → the one character replies". It is:

```
director picks the next speaker → that actor speaks into the scene →
the line becomes part of every actor's dialogue window → repeat
```

The **user steps out of the cast**. Instead of being an actor whose words move a
character's bond, the user becomes the **narrator / suffleur**: they feed cues
("Kaguya notices Megumin bragging again", "a knock at the door") that steer the
scene without being *spoken to*. This reuses the runtime's three-role split:

- **source** — who delivered the line (user-as-narrator, or an actor).
- **speaker** — who *owns* the words (an actor, or nobody for a stage cue).
- **subject** — who it is about.

Rules carried over from ADR-0008, adapted to the pack tier:

- A narrator cue is an **observation**, not speech. Actors react to the *event*
  ("why are you smirking?"), they never answer the narrator ("thanks for
  telling me").
- Relationship axes move **only** relative to a real speaker. Actor→actor lines
  move the *listening actor's* state toward the *speaking actor*, never toward
  the user. A bare stage cue is mood-only.
- A cue is a signal, not a guaranteed turn — the director decides whether it
  warrants a spoken reaction (see capability 4), so the scene doesn't chatter on
  every prompt.

This is the headline: **the user can direct a play instead of being in it.**

### 3. A background, loaded from the web UI, pinned into context

The web shell can upload an image; a vision-capable model produces a **detailed
description** of it once, and that description is **pinned into the context
window as a stable block** — part of the KV-cached prefix, next to the actors'
identities — and stays there until the background is changed.

- The picture is read **once** (a vision pass → text), never re-sent per turn.
  Only the text description lives in context, which keeps every subsequent turn
  cheap and keeps the backdrop *consistent* across the whole scene.
- It is a **shared** block: every actor in the scene sees the same backdrop, so
  they can reference "the rain outside" or "this cramped meeting room" coherently.
- Changing the background = one new vision pass → the pinned block is replaced
  (and the prefix cache for that block invalidated). This mirrors how the full
  runtime turns a screen frame into a text caption before it ever reaches the
  character (privacy/economy: pixels become words at the edge).

### 4. Who speaks next — narrator-directed or model-directed

Turn-taking is decided by a **Director**, and there is a switch for *who* the
director is:

- **Narrator-directed** — the user/suffleur names the next speaker (explicitly,
  or implicitly by addressing a cue at one actor). Deterministic, good for
  scripted scenes and for the runner.
- **Model-directed** — an LLM call picks the next speaker from the cast, exactly
  the way the **moment-tag classifier** already picks a tag from a closed enum.
  The choice set is the actor ids; an invalid/empty pick falls back to a default
  (e.g. last speaker's addressee, or round-robin).

**This is the same mechanism as tags, one level up.** The tag classifier chooses
*which steering block* to splice into one character's tail; the director chooses
*which actor's cache* to make active. Selecting a speaker **swaps the active
pinned prefix**: the chosen actor's KV-cached identity becomes the live context,
the previous actor's is set aside (not destroyed — held warm for when they speak
again). On a switch, the active cache is *replaced*, not rebuilt from scratch —
which is why holding several actors stays affordable.

```
one character (v0.1):   tag classifier → steering block → voice
several characters (v0.2): director → active actor cache → tag classifier
                            → that actor's steering block → voice
```

## How it maps onto what already exists

| v0.2 concept        | v0.1 seam it extends                                        |
|---------------------|------------------------------------------------------------|
| Scene / cast        | `SessionStore`, keyed `(scene_id, actor_id)` per actor      |
| ActorState          | today's `(pack, StateKernel, memory)` bundle, unchanged     |
| Actor swap / cache  | the two-segment pinned prefix (already KV-cache friendly)    |
| Director (speaker)  | a second classifier, twin of `TagClassifier` over actor ids |
| Narrator / suffleur | the `source ≠ speaker ≠ subject` split; observation vs speech|
| Backdrop            | a pinned prefix block fed by a one-shot vision caption       |
| Per-turn steering   | the moment-tag delta table + steering blocks, **per actor**  |

New wire surface (sketch, to be pinned in the spec when built):

- A **Scene** resource: create with a cast (pack ids) + director mode; advance a
  turn (with an optional narrator cue); read the transcript. Likely alongside
  the OpenAI-compatible route rather than inside it, since a scene turn is not a
  single request/response.
- Narrator cues carry `event_type: observation | speech` and a `speaker` (an
  actor id, or none for a bare stage cue).
- Background upload endpoint → vision caption → pinned `backdrop` block.

## Invariants kept

- **Single-user by design.** A scene is still one person's private play.
- **No character-shaped defaults in the engine.** Actors, director prompts, and
  the narrator framing are all pack/deployment data, never baked into the engine.
- **State is the engine's, never the model's.** Axes still move only from the
  per-tag delta table, per actor; the model never sees or writes the numbers.
- **KV-cache economy.** Adding actors adds pinned prefixes, not per-turn cost;
  the backdrop is captioned once, not re-sent.
- **The narrator is a sensor, not a cast member.** Never answered, only reacted
  to — the load-bearing rule that keeps "direct a play" from collapsing back into
  "chat with a bot".

## Open questions (decide before building)

1. **Turn budget / stop condition** for autonomous actor↔actor exchange — how
   many actor turns fire per narrator cue before it waits for the next cue?
   (Mirror the runtime's salience/frequency gate so a scene doesn't run away.)
2. **Director default** in model-directed mode when the pick is empty/invalid —
   round-robin, last-addressee, or "narrator must choose"?
3. **Memory scope** — does each actor remember the whole scene, or only lines
   addressed to/spoken by them? (Leaning: each actor remembers what it witnessed.)
4. **Vision model** — reuse an Ollama multimodal model (as the runtime does), or
   make the backdrop caption a plain text field the user can also type by hand
   (no vision dependency in the community tier)?
5. **Scene persistence** — extend the `.local/sessions` layout to a
   `.local/scenes/<scene_id>/` tree (per-actor state + one shared transcript)?

## Non-goals

- Not a multi-*user* system — still one director at the keyboard.
- Not an agent framework — actors act *within a scene*, they do not take real
  actions in the world (no tools, no safe-chain; that stays out of this tier).
- Not a rewrite — v0.2 is an extension of the v0.1 Actor Model, gated so a
  single-actor scene behaves exactly like v0.1 does today.
