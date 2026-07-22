# Design — v0.2: a cast, a stage, and a web of feelings

> **Status: design, not built yet.** This is the plan for v0.2, written down so
> we agree on the shape before writing code. Everything here grows out of the
> v0.1 pieces we already have — it does not throw any of them away.

## The short version

Today one character talks to you, and remembers how it feels about *you*.

v0.2 puts **several characters on the same stage**. Each one keeps its own
feelings — about you *and* about every other character. You can either **join the
group chat** and talk with all of them, or **step back and direct**, feeding the
scene cues while the cast acts among themselves. You can also set the **backdrop**
by uploading a picture, and let either you or the model decide **who speaks next**.

That's the whole idea. The rest of this doc explains each part in plain terms and
shows how it reuses what v0.1 already does.

## From one character to a cast

In v0.1 a character is two things glued together:

- a **"who I am" block** that's written once and pinned at the top of the prompt
  (this is what makes it cheap — the model caches it and doesn't re-read it every
  turn), and
- a small **running tally** of affection / trust / bond toward you.

A second character is just a second "who I am" block and a second tally. So
holding a cast of characters is not a rewrite — it's the same pieces, more than
one of each. Adding an actor adds a pinned block; it doesn't make every turn more
expensive.

A **Scene** is the thin thing that holds them together: the cast, the backdrop,
who's directing, and — the important new piece — the **web of feelings** between
everyone in it.

## Everyone keeps their own feelings — the relationship matrix

This is the heart of v0.2.

In v0.1 there's exactly one relationship: *character → you*. In a scene there are
many, and they point in **both directions independently**. Picture a grid where
each row is "how this one feels about the others":

```
   feels about →     You        Megumin      Kaguya
   ┌─────────────────────────────────────────────────
   You         │      —          fond of      curious about
   Megumin     │   adores you    —            looks up to
   Kaguya      │   polite        exasperated  —
```

Every cell is its **own** little relationship — its own affection, trust, and
bond — and it moves on its own. Two things fall out of that:

- **Feelings are directed, not shared.** Megumin looking up to Kaguya is a
  *different* thing from Kaguya's feelings about Megumin.
- **Feelings are not necessarily mutual.** Megumin can genuinely admire Kaguya
  while Kaguya finds her exhausting. Warmth on one side does not force warmth
  back — each side only changes on *that character's own turns*, from what
  *they* just experienced.

That asymmetry is the point. It's what makes a group feel like real people
instead of a set of mirrors: crushes that aren't returned, a rivalry only one
side is invested in, someone you trust who doesn't quite trust you back.

*Under the hood:* it's the same per-character tally from v1, just one per
**pair** instead of one per character. When Megumin reacts to something Kaguya
did, only the **Megumin → Kaguya** cell moves. The engine still owns those
numbers; the model never sees them — it only receives the *tone* they select,
exactly like today.

## Two ways to be in a scene

The web of feelings is always there. What changes between modes is **where you
sit**.

### Group chat — you have a seat

You're one of the participants. You talk to the group (or to one character by
name), they answer, and they answer *each other* too. Everyone updates their
feelings about everyone — including you. This is the natural "hang out with the
whole cast" mode: your row and column in the grid are live, right alongside the
character-to-character ones.

### Directing a play — you're the narrator

You step out of the cast and become the **prompter** (the *suffleur*). Instead of
being talked to, you feed the scene **cues** — "a knock at the door", "Kaguya
notices Megumin bragging again" — and the characters act them out among
themselves.

The load-bearing rule here, borrowed from the full M.A.R.I.A. runtime: **the
narrator is a stage direction, not a person in the room.** A character reacts to
the *event* ("what are you smirking at?") but never answers *you* ("thanks for
telling me"). That one rule is what keeps "directing a play" from quietly
sliding back into "chatting with a bot". In this mode your own row in the grid
stays quiet — you're steering the scene, not in it.

## ScenePack — the production

A Character Pack is a **portable actor**: it knows who it is, but nothing about
any particular play. A **ScenePack** is the **production** that casts actors into
a scene. It's a second, separate pack type, and it never edits the characters —
it *composes* them.

A ScenePack says:

- **The cast** — which Character Packs to bring on stage (by name).
- **The setting** — the shared premise and backdrop, in words: where everyone is,
  what's going on, the theme of the "play". Pinned for the whole cast (the
  authored twin of the uploaded-image backdrop below).
- **Starting feelings** *(optional)* — seed the relationship matrix so the cast
  doesn't always begin as strangers: an old rivalry, a one-sided crush, a settled
  friendship, already loaded at curtain-up.
- **Scenario-only tags** *(optional)* — extra moment-tags the *setting* grants
  specific characters, layered on top of their base ones just for this scene.

That last part is the fun one. A character's base pack is neutral and portable; a
ScenePack can give an actor ways to react that only make sense *here*.

> **Example.** A **fantasy** ScenePack drops the cast into a world of magic. For
> Kaguya — a modern heiress who has never seen a spell — it adds a scenario tag
> **`fantasy_shock`**: *"Kaguya is meeting the impossible for the first time and
> is quietly reeling."* Now, when the scene throws magic at her, the classifier
> can pick that tag and she reacts with real culture-shock — something her base
> pack, written for a student-council comedy, would never produce. Megumin, born
> to explosions, gets no such tag; the same setting lands on each actor
> differently.

*Under the hood:* a scenario tag is just an ordinary tag (id, delta, block) added
to that character's closed list **for the duration of the scene**. Nothing new is
needed — the character simply has a slightly bigger vocabulary while this
ScenePack is loaded, and goes back to its neutral, portable self when the scene
ends.

So the layering is clean:

```
Character Pack   =  who an actor is       (portable, reused across scenes)
ScenePack        =  a production           (cast + setting + starting feelings + scene tags)
Scene (runtime)  =  a loaded ScenePack     (now with live feelings and a transcript)
```

## A backdrop you can set from the web page

Upload a picture in the web UI. The model **looks at it once**, writes down a
detailed description of what it sees, and that description gets **pinned into the
scene** as the set — shared by everyone on stage, so they can all refer to "the
rain outside" or "this cramped meeting room" and stay consistent.

Two things worth saying plainly:

- The picture is read **once**, turned into words, and only the words stay in
  context. Every turn after that is just as cheap as before, and the backdrop
  stays the same until you change it.
- Change the picture → one new look → the pinned description is swapped out. (The
  full runtime already does exactly this trick with what's on screen: turn the
  image into a caption at the edge, and only the caption travels inward.)

## Who speaks next

Someone has to decide whose turn it is. That's the **director**, and there's a
switch for who plays that role:

- **You decide** — you name who speaks next, or just address a cue at someone.
  Predictable; good for scripted scenes.
- **The model decides** — a quick model call picks the next speaker from the
  cast, the same way v1 already picks the "moment tag" from a fixed list. If it
  picks nothing sensible, we fall back to a simple rule (round-robin, or whoever
  was just addressed).

Here's the neat part: **this is the tag mechanic, one level up.** In v1 the
classifier picks *which mood block* to splice into one character's prompt. In v2
the director picks *which character's cached "who I am" block* to make active.
Choosing a speaker just **swaps which pinned block is live** — the previous
character's block is kept warm for when they speak again, not rebuilt from
scratch. That's why holding several characters stays cheap.

## How it reuses what's already here

| v0.2 idea                 | The v0.1 piece it grows from                          |
|---------------------------|-------------------------------------------------------|
| A cast on one stage       | Several of today's pinned "who I am" blocks           |
| ScenePack                 | Composes today's Character Packs; loads them as-is     |
| Relationship matrix       | Today's affection/trust/bond tally — one per **pair** |
| Scenario-only tags        | Just more entries in a character's existing tag list  |
| Switching who's talking   | The two-segment prompt (already cache-friendly)       |
| The model picking speaker | A twin of today's moment-tag classifier, over names   |
| Narrator / cues           | The "who delivered ≠ who spoke ≠ who it's about" split |
| The backdrop              | A pinned block filled by a one-shot look at an image  |

## What stays true

- **Still one person's private world.** A scene is your play, or your group chat
  — not a multi-user server.
- **No character baked into the engine.** The cast, the director, the narrator's
  framing — all of it is data you load, never wired into the code.
- **The numbers belong to the engine, not the model.** Every feeling in the
  matrix is moved by the engine from a clear table; the model only ever feels the
  *tone*, never reads or writes the score.
- **Adding characters doesn't make turns more expensive.** More cast = more
  pinned blocks, not more per-turn work. The backdrop is looked at once, not
  re-sent.
- **The narrator is never a cast member.** Reacted to, never answered.

## Still to decide

1. **How long do the characters riff before pausing?** When the cast is talking
   among themselves, how many turns fire before it waits for your next cue — so a
   scene doesn't run away on its own?
2. **When the model can't pick a speaker,** who talks — round-robin, whoever was
   just addressed, or "you choose"?
3. **How much does each character overhear?** Does everyone remember the whole
   scene, or only the lines aimed at or spoken by them? (Leaning: you remember
   what you witnessed.)
4. **Do character-to-character feelings drift on their own,** or only when the
   two actually interact? (e.g. does Megumin's crush fade if Kaguya ignores her
   for a while?)
5. **The backdrop's picture** — the ScenePack's `setting` text already covers the
   authored/typed case with no vision model needed; the open part is just the
   *image* upload — reuse a vision model (as the full runtime does) as an
   optional extra, on top of the always-available typed setting?
6. **Where a scene is saved** — extend today's `.local/sessions` into a
   `.local/scenes/<id>/` folder holding each pair's tally plus one shared script?

## What this is not

- Not multi-*user* — still one person at the keyboard, whether directing or
  chatting.
- Not an agent framework — the cast acts *within the scene*. They don't touch the
  real world (no tools, no file or command access; that stays out of this tier).
- Not a rewrite — v0.2 is the v0.1 Actor Model with more chairs. A scene with a
  single character behaves exactly like v0.1 does today.
