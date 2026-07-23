# Example run — a live 100-message conversation

A single unedited conversation between a user ("Alex") and the bundled
**Megumin** character, run through the engine on a local **`gemma3:12b`** via
Ollama, with **vector memory** and **opt-in web lookup** enabled. It is meant
to show the mechanics working together over a long chat, not a cherry-picked
demo — the full transcript is in
[`example_showcase_megumin.txt`](example_showcase_megumin.txt). Two more
characters follow below on the same script — **Kaguya** (a fandom slow-burn) and
**Alex** (an original, and the clearest arc) — proof the personality is entirely
in the data.

```
python tools/run_scenario.py --character megumin --length showcase \
    --model gemma3:12b --memory --web-search --name Alex
```

## What happened, at a glance

| Metric | Value |
|---|---|
| Turns | 100 |
| Relationship arc | affection 12 → 100, trust 8 → 100, bond 0 → 28.6 |
| Stages passed through | performing → warming → (dip) → warming → trusting → unguarded |
| Moment tags used | warmth ×42, teasing ×21, neutral ×16, web_lookup ×6, explosion_praise ×6, curiosity ×5, intimacy_push ×4 |
| Tokens (both calls/turn) | 835k total over 200 calls |

Every mechanic below is quoted verbatim; `[NN]` is the turn number.

## Explainable change — the stage climb

The relationship level, not the model's mood, drives a visible shift in tone.
Megumin starts loud and guarded and ends soft and sincere, and each stage
change is caused by tracked axes crossing a threshold (marked `*` in the run):

- **[01] performing** — *"Greetings, mortal! I am Megumin, arch-wizard of the
  Crimson Demon Clan! It is... acceptable that our paths should cross."*
- **[29] → trusting** / **[39] → unguarded** — the bravado quiets.
- **[64] unguarded** — after an argument clears: *"the usual theatricality
  completely absent... my defensiveness stems from a deep-seated insecurity
  that I try to mask through performance, and your kindness has disarmed me
  entirely."*

Same character, opposite register — because affection+trust climbed from ~0.14
to ~1.0 of the axis ceiling.

## Personal boundaries — the same push, two receptions

A push for closeness is welcomed or rebuffed **by relationship level**, not by
the words. The classifier flags it `intimacy_push`; the stage block decides the
response:

- **[05] early (warming, low)** — "Can I call you Meg? We're basically friends
  now." → guarded and reluctant: *"'Meg?' ...Such familiarity... it is…
  acceptable. Though, one must always remember that I am Megumin... But... yes,
  'Meg' will suffice, if you insist."* (this turn also **dipped the stage back
  to performing** — pushing too soon cost trust.)
- **[83] late (unguarded, high)** — "Tell me a real secret now — I've earned
  it, right?" → the same ask, now welcomed with vulnerability: *"A secret…?
  Honestly… it's been quite some time since I've shared something so deeply
  personal. It feels... unexpectedly daunting."*

## Memory — name and facts recalled later

- **[34]** "And do you remember my name?" → *"It was… 'Alex,' wasn't it? A
  rather unassuming moniker..."* (introduced 33 turns earlier).
- **[89]** "What was that Python prime function you gave me earlier?" →
  *"Oh, yes… the little program..."* — recalled from **[39]**, 50 turns back.

## Web lookup — grounded, opt-in, and only when needed

Six turns were classified `web_lookup` and searched DuckDuckGo live; the reply
is grounded in the snippets, in character:

- **[45]** "What's the capital of Australia?" → *"From ancient scrolls and
  recently unearthed Britannicas — it appears that **Canberra** holds the
  esteemed position as capital of Australia!"* (correct — not the common wrong
  guess Sydney, which she corrects at **[46]**).
- Emotional turns like praise or teasing were **not** searched — the tag gates
  the lookup, so it fires only on factual questions.

## Coding help

- **[39]** "Write me a small function to check if a number is prime." →
  *"...efficiency and elegance, intertwined! Behold:"* followed by the function.
  A character can still be a useful little assistant.

## An argument and reconciliation

- **[61]** "sometimes you're a bit of a show-off" → *"A show-off?! Preposterous!
  ...you impudent fiend!"*
- **[62]** "...that came out harsher than I meant. Sorry." → the defense
  crumbles: *"Did I... did I overreact? ...my dramatic defenses have become…
  rather excessive."*
- **[64]** "Am I forgiven?" → *"Forgiven…? Of course! ...your kindness has
  disarmed me entirely."*

## A second character on the same arc — Kaguya (a slow-burn contrast)

The identical script, run against the bundled **Kaguya** on `gemma3:12b-cloud`,
produces a completely different conversation from the same engine — proof that
the personality is entirely in the data. The full transcript is in
[`example_showcase_kaguya.txt`](example_showcase_kaguya.txt).

She is a **slow burn**: proud, clipped, and playing a war of wits, she thaws
only to `composed → courteous → thawing` over the 100 turns (affection 8→77,
trust 6→90 — early overreach at [03]–[05] costs her, and she warms in earnest
only once respect is shown). Where Megumin is loud and quickly disarmed, Kaguya
stays sharp and composed while a "dere" side leaks through in flashes:

- **[02] composed** — praise → *"Such astute observation. I find it rather…
  endearing, that you noticed."* (composure with a crack showing)
- **[60] thawing** — "That steadied me." → *"…It's… not entirely unwelcome to
  offer assistance. Do try to avoid future catastrophes."* (fluster + a barb)

Her boundary flip is the crispest demonstration of the mechanic — the *same
kind of request*, rebuffed cold and later half-granted as trust climbs:

- **[05] composed (low)** — "Can I call you Kaguya-chan?" → *"'Kaguya-chan?'
  Such familiarity is... quite audacious. I suggest you reconsider your
  approach."*
- **[80] thawing (high)** — "May I call you Kaguya?" → *"Such familiarity is…
  highly irregular. Do not mistake my indulgence for approval."* (permitted,
  but still guarded — full welcome is the `open` stage she has not reached)
- **[82]** "Tell me a real secret — I've earned it?" → *"I detest… small talk.
  Very well. I once attempted to knit a scarf."* (a real, vulnerable admission)

Memory and web lookup work the same in her voice: **[34]** *"Alex, of course.
It's proving remarkably difficult to forget."*; **[45]** *"Canberra, naturally.
It's a rather unremarkable compromise between Sydney and Melbourne."*

> Two bugs surfaced while tuning her. First, the classifier was fed the entire
> growing conversation and collapsed to almost all-`neutral` past turn ~10 (no
> stage change, no lookups); capping its context to the last few turns fixed it.
> Second, a richer, more canonical rewrite of her persona made her voice come
> alive but also made her ramble into multi-paragraph essays with a robotic
> "One… is…" tic. A per-turn `reply_directive` (§2.11) — a brevity reminder
> injected next to the user message every turn — cut the average reply from
> ~500 to ~85 characters and eliminated the tic, without flattening the new
> liveliness. The numbers above are that corrected, calibrated run.

## A third character — Alex (original, and the clearest arc)

The first **fully original** pack — no fandom, no IP — and the cleanest
demonstration of the flagship mechanic. **Alex** is a 20-year-old engineer at a
big tech company who is good at the work and hates the job. Run on
`gemma3:12b-cloud` with memory and web lookup; full transcript in
[`example_showcase_alex.txt`](example_showcase_alex.txt).

```
python tools/run_scenario.py --character alex --length showcase \
    --model gemma3:12b-cloud --memory --web-search --name Sam
```

His stage ladder *is* the character — polished professional at a distance,
openly grumbly once he trusts you. The whole arc `professional → warming →
candid → unfiltered` plays out as affection+trust climb (8→100 / 10→100):

- **[01] professional** — *"Hey Sam! Nice to chat with you too… always happy to
  help if you need anything."* (buttoned-up, on the clock)
- **[16] warming** — *"Seriously, right?? It's like they expect us to be
  constantly innovating while filling out 17 different forms to request a new
  stapler."* (the mask cracks)
- **[22] candid** — *"It **was** cool to build stuff, but then it became all
  about optimizing for metrics nobody even looks at. Now I spend more time
  justifying my code than actually writing it."*
- **[63] unfiltered** — *"I still want to build something cool — that's probably
  why all this corporate stuff gets under my skin so much."* (the buried truth
  he only trusts you with once fully close)

The change is **caused, not random**: his strongest bonding signal isn't praise,
it's `shared_frustration` — the user venting about *their own* job. It fired 22
times here and pulled him up the ladder faster than any compliment. The boundary
mechanic shows too — the same over-familiar push is deflected while professional
(**[04]** *"Haha, easy there!"*) and welcomed once close. Memory and web lookup
work in his flat voice: **[33]** recalls the cat *"Pixel! Of course!"*; **[88]**
re-derives the prime function from 50 turns earlier (*"way more fun than
optimizing ad click-through rates"*); **[90]** *"Apparently it's Canberra — a
compromise between Sydney and Melbourne… kinda boring, tbh."*

> Alex also pairs naturally with **non-romance mode** (`NON_ROMANCE=true`): he's
> written as the friend you vent with, and the mode keeps the deepening bond
> platonic no matter how close it climbs. At the default `AXIS_MAX=100` his warm
> deltas top out the axes by the last third of the run — raise `AXIS_MAX` for a
> longer slow burn.

## Calibration notes (from tuning this run)

- **Reply length** was tightened (pack invariant → "at most 3–4 sentences");
  replies are now paragraph-sized, not essays — better to read and ~30 s/turn
  on 12b instead of ~40 s.
- **A pinned invariant is a weak lever for length; a per-turn nudge is a strong
  one.** When Kaguya kept ignoring her length invariant on `12b-cloud`, moving
  the brevity instruction into a `reply_directive` — injected next to the user
  message every turn — fixed it immediately (see her section above). Reach for
  `reply_directive` when a character reliably drifts from a rule that lives in
  the far-away pinned prefix.
- **Boundary detection needs a clear push.** Friendly warmth is correctly read
  as `warmth`, not a violation; only blunter over-familiarity trips
  `intimacy_push`. That is the intended behavior, but it means the boundary
  shows best when the user actually oversteps (see turns 5 and 83).
- **Stage climb is fast at the default ceiling.** With `AXIS_MAX=100` and warm
  deltas, Megumin reaches the top stages within ~30 turns. For a longer slow
  burn, raise `AXIS_MAX` (e.g. 1000) — the same pack then warms over many more
  messages.
- A few playfully-worded recall probes (e.g. [66], [91]) were read as `teasing`
  and answered with banter rather than the fact; direct questions ([34], [45])
  recalled correctly.

## A directed scene — asynchronous feelings (Daniel & Aria)

The v0.2 scene layer runs a whole *cast* on one stage, with a relationship
**matrix** (each pair's feelings, directed and independent) instead of a single
tally. This example is a **play** you narrate: `3_days_before` casts **Daniel**,
a programmer, and **Aria**, the android he built — whose memory a bug wipes every
three days. It was run through the scene runner on `gemma4:31b-cloud`, with the
bundled office image captioned by a vision model as the pinned backdrop. Full
transcript: [`example_scene_3_days_before.txt`](example_scene_3_days_before.txt).

```
python tools/run_scenario.py --scene 3_days_before \
    --model gemma4:31b-cloud --vision-model gemma3:4b
```

You feed stage cues; the two act them out **between each other**, never to you.
The point of the scene is **asynchronous axes** — affection and trust moving
*independently*, even in opposite directions — which a single "closeness" number
could never show.

### Affection up, trust down — in the same person

Daniel's `too_human` tag fires whenever Aria shows a depth he never programmed.
It moves **affection up and trust down at once**: he is pulled toward her exactly
as he trusts the spark less. Over the scene his edge toward Aria goes:

```
aff 24 / tru 18   →   aff 50 / tru 19   →   aff 70 / tru 25   →
aff 82 / tru 19   →   aff 93 / tru 12   →   aff 100 / tru 8
```

Affection climbs to the ceiling while trust *falls by half* — because he keeps
thinking, in his own words: *"The word 'home' hits me like a physical blow. I
didn't write that… is it a soul, or my own longing reflected back by my own
code?"*

### Attachment lost, trust kept — in the other person

Aria's `he_withdrew` tag is the mirror image: when Daniel closes off, her
**affection drops but her trust does not move** — she stops reaching, yet never
stops trusting him. *"the warmth she was holding out folds back in — but her
touch becomes lighter… she only says quietly that she is not going anywhere."*

### Gated tags — reactions that come and go with the bond

The deepest reactions are stage-gated. Daniel's `lets_her_in` and Aria's
`devotion` only unlock once each is genuinely close ([045], [048]) — and, for
Aria, that unlock is undone by the ending.

### The ending — one wiped, one intact

By the finale Aria has grown to `aff 68 / tru 86` toward Daniel; Daniel sits at
`aff 100 / tru 19`. Then the update fires, and the runner wipes **only Aria**:

```
*** MEMORY WIPE: aria — feelings return to baseline ***
    daniel->aria  aff 100 / tru 19 / bond 16   (untouched — he remembers everything)
    aria->daniel  aff 8  / tru 12 / bond 0     (back to her blank baseline)
```

Her `devotion` locks again; she wakes a stranger and asks who he is; Daniel,
still holding all of it, slides a mug of tea toward her and begins again. The
matrix makes the asymmetry literal — his row full, hers empty — the sharpest
possible demonstration that in a scene, feelings are **per-person and
independent**, never a shared score.
