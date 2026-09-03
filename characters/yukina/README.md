# Yukina — sample character pack

Your adorable Minecraft girl. She builds, she chatters, and she will absolutely
punch you for ignoring her.

An original character written for this engine, so it ships under a real content
licence (CC-BY-4.0) rather than as a fan work.

## What it demonstrates

The other sample packs answer "how does she react to this message". Yukina is
here to show the shape of a character whose reactions have somewhere to land:
she is a **game** character, and the same closed tag set that steers her voice
can steer a body in a world (see `docs/GAME_PORT.md`).

Two things in the pack are worth reading as design rather than flavour:

- **`neglect` is a first-class tag with a real cost.** Most packs have one
  negative tag for rudeness. Yukina has one for *inattention* — a one-word
  answer, a subject change away from her — and it moves the axes down harder
  than teasing does. A character who only reacts to what you say to her cannot
  notice that you have stopped saying anything.
- **`teasing` is POSITIVE for her.** Her deltas move affection *up* when she is
  needled, because that is the game she is playing. The same tag is negative in
  Megumin's pack. That is the point of the format: the tag names the moment,
  and the pack decides what the moment is worth.

The punch is gated by stage, not by prose: at `newcomer` the stage block says
she keeps her hands to herself, and only from `friends` on does the shoving
start. A pack cannot enforce that with a rule the model might ignore, but it
can make it the character's own tone at that distance.

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

That one-character message is the fastest way to see `neglect` fire.

## No art is bundled

The `sprites` map is intentionally absent. Add your own images under
`sprites/` and map them in `pack.yaml` if you want a face to go with the voice.
