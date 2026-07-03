# M.A.R.I.A. Micro-Engine

A lightweight, character-pack driven chat engine with an OpenAI-compatible API.
Give it a character as **data** and it plays that character — reacting to each
message and, over a whole conversation, **visibly changing** as the
relationship grows.

- **Engine** (`engine/`) — generic character runtime: YAML character packs,
  three relationship axes (affection / trust / bond) moved by an explicit
  delta table, prompt assembly from named fragments. No character is built in:
  without a pack the engine honestly reports that nothing is loaded.
- **App** (`app/`) — thin FastAPI layer exposing an OpenAI-compatible API plus
  a small browser shell, so existing OpenAI clients (or a web page) can talk to
  a character by pointing at this server.

## Quickstart

```bash
make install                  # or: pip install -r requirements.txt
make model                    # or: ollama pull gemma3:12b  (any Ollama model works)
make run                      # or: uvicorn app.main:app --reload   → serves on :8000
```

Open <http://127.0.0.1:8000/> for the browser shell — pick a bundled character
(Megumin or Kaguya), chat, and watch the affection/trust/bond bars and the
relationship **stage** shift as you go. Or talk to it as an OpenAI-compatible
endpoint, using the character name as the `model`:

```bash
curl http://127.0.0.1:8000/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model": "megumin", "user": "me",
       "messages": [{"role": "user", "content": "your explosions are amazing"}]}'
```

The response is a standard chat completion plus an `x_micro_engine` field
carrying the active `tag`, `stage`, `stage_changed`, `sprite`, and axis values.

## The headline: characters that change, explainably

The moment tag is the *weather* — how the character reacts to this message. The
**stage** is the *climate* — who they are as the relationship deepens. A
character can start loud and guarded and grow calm and warm, and every shift is
caused by tracked numbers you can inspect, not by the model's mood. Want a long,
slow arc? Raise the axis ceiling with `AXIS_MAX=1000` and the same character
warms across many more messages. See [CHARACTER_PACK_SPEC.md](CHARACTER_PACK_SPEC.md).

## Make a character

A character is just data — a `pack.yaml` (plus optional sprites). Read the
[spec](CHARACTER_PACK_SPEC.md), copy a pack under [characters/](characters/),
and drop yours in `characters/<name>/`. To share it, see
[CONTRIBUTING.md](CONTRIBUTING.md).

## What this is (and isn't)

This is the **community tier**: a deliberately simple engine — an LLM picking
one tag from a YAML enum, numbers moved by a table, tone shaped by prompt
blocks. There is no machine-learning perception, no file or command access, no
agent loop. That simplicity is the point: it's easy to read, fork, and author
for.

It is the visible tip of a larger, private project. The full **M.A.R.I.A.**
perceives and remembers very differently, and is not open source. If the tip
interests you, the rest lives at the hub:

**→ [The M.A.R.I.A. hub](https://github.com/HontoUKI/M.A.R.I.A.)**

## Contributing

Code PRs are not merged — the engine is author-driven (fork freely, it's
Apache-2.0). The community contribution is **characters**. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [SUBMISSION_TERMS.md](SUBMISSION_TERMS.md).

## License

Engine code: **Apache-2.0**. Sample character *content* is licensed separately —
each pack under `characters/` has its own README and `meta.license`.

> Work in progress — v0.1. Expect rough edges.
