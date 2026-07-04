# Example run — a live 100-message conversation

A single unedited conversation between a user ("Alex") and the bundled
**Megumin** character, run through the engine on a local **`gemma3:12b`** via
Ollama, with **vector memory** and **opt-in web lookup** enabled. It is meant
to show the mechanics working together over a long chat, not a cherry-picked
demo — the full transcript is in
[`example_showcase_megumin.txt`](example_showcase_megumin.txt).

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

## Calibration notes (from tuning this run)

- **Reply length** was tightened (pack invariant → "at most 3–4 sentences");
  replies are now paragraph-sized, not essays — better to read and ~30 s/turn
  on 12b instead of ~40 s.
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
