# Yukina — sample character pack

Your Minecraft girl. She builds, she chatters, she keeps count of every minute
you are gone — and the fonder she gets, the less she is willing to let the world
near you.

An original character written for this engine, so it ships under a real content
licence (CC-BY-4.0) rather than as a fan work.

## What it demonstrates

The other sample packs answer "how does she react to this message". Yukina
answers a harder one: **what becomes possible for a character only after she is
attached** — and she answers it in the engine, not in prose.

She is also a **game** character: the same closed tag set that steers her voice
can steer a body in a world (see `docs/GAME_PORT.md`).

### The gates are code, not a request to the model

Six of her eighteen tags carry an availability window (`unlock_at` / `lock_at`)
on the closeness ratio. Outside its window a tag is **never shown to the
classifier**, so the model cannot choose it — and a model that names it anyway
gets the pack's fallback. This is the difference between "we asked her not to be
jealous yet" and "there is no jealousy in the list she is choosing from".

| ratio | what opens |
|---|---|
| `0.00` | the ordinary reads: attention, warmth, praise, **gift**, **watched**, teasing, neglect, insult |
| `0.45` | `he_left` · `he_is_in_danger` · `someone_else` — she starts to guard, to miss, and to mind who else is there |
| `0.70` | `intimacy_return` replaces `intimacy_push`, and `told_to_back_off` appears — being sent away becomes something she has a reaction to instead of simply obeying |

Both edges are inclusive, so on the threshold itself the two sides of the
romance gate are briefly available together; `tests/test_yukina_pack.py` pins
that rather than leaving it to be discovered in play.

### Two numbers that carry the whole character

- **A gift is the single largest thing he can do** (`affection +8`, more than
  praise, warmth or attention). Armour, a tool, gold, a diamond — anything he
  went and got. The reasoning is in the pack: everything else good happens while
  she is standing there, and a gift is proof somebody thought about her while
  she was not.
- **Leaving her does not cool her off — it concentrates her.** `he_left` is the
  only row in the delta table whose axes point in *opposite* directions:
  `affection +1`, `trust −3`. She reaches harder for the person she can rely on
  less, and because closeness is the average, the gate ratio still falls. The
  yandere arc is written in arithmetic rather than adjectives.

### Kept from the previous version

- **`neglect` is a first-class tag with a real cost.** Most packs have one
  negative tag for rudeness. Yukina has one for *inattention* — a one-word
  answer, a subject change away from her — and it moves the axes down harder
  than teasing does. A character who only reacts to what you say to her cannot
  notice that you have stopped saying anything.
- **`on_your_own` exists because `neglect` is that strong.** With a game attached
  she gets notes from the world in square brackets — `[closed]`, `[waiting]`,
  `[interrupted]` — and they arrive on the same channel as a player's line. Live
  08.09 a `[closed]` two seconds after she had answered read as `neglect`, and her
  own block says what to do about that: needle them, then punch them in the arm.
  She did, seven times, to somebody who was talking to her the whole time. The tag
  costs nothing on any axis, because nobody did anything. The same rule now covers
  `he_is_in_danger`: night falling on him is a state of affairs, not something he
  did, so it moves nothing and only changes what she does next.
- **`teasing` is POSITIVE for her.** Her deltas move affection *up* when she is
  needled, because that is the game she is playing. The same tag is negative in
  Megumin's pack. That is the point of the format: the tag names the moment, and
  the pack decides what the moment is worth.

The punch is gated the same way the possessiveness is: at `newcomer` the stage
block says she keeps her hands to herself, and only from `friends` on does the
shoving start.

## Her arc

`newcomer` → `friends` → `possessive` → `devoted` → `inseparable`. Each stage
block says what she is like at that distance; the tag windows say what she is
*able to notice* there. The two are set at the same thresholds on purpose — a
character who becomes possessive at one number and gains jealousy at another
reads as two separate changes.

## Everything stays inside the game

An invariant in the pack says so plainly: what she wants, threatens or promises
happens in blocks, doors, torches, mobs and the walk home. Possessive, never
punishing — she shoves, sulks, blocks a doorway and refuses to leave, and when
something is actually about to kill him she is the thing standing in front of it.

## Try it

```bash
uvicorn app.main:app
# then open http://127.0.0.1:8000/ and pick Yukina
```

Or as an OpenAI-compatible endpoint, with the pack name as the model:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H 'content-type: application/json' \
  -d '{"model": "yukina", "messages": [{"role": "user", "content": "k"}]}'
```

That one-character message is the fastest way to see `neglect` fire. To see a
gate instead, say the same affectionate line at the start of a session and again
after a long warm one: the first is `intimacy_push`, the second cannot be.

## No art is bundled

The `sprites` map is intentionally absent. Add your own images under
`sprites/` and map them in `pack.yaml` if you want a face to go with the voice.
