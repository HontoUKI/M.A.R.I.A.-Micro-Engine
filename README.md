# M.A.R.I.A. Micro-Engine

[![CI](https://github.com/HontoUKI/M.A.R.I.A.-Micro-Engine/actions/workflows/ci.yml/badge.svg)](https://github.com/HontoUKI/M.A.R.I.A.-Micro-Engine/actions/workflows/ci.yml)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](pyproject.toml)
[![Backends: Ollama · OpenAI](https://img.shields.io/badge/backends-Ollama%20%C2%B7%20OpenAI-orange.svg)](.env.example)

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

The response is a standard chat completion (including token `usage`) plus an
`x_micro_engine` field carrying the active `tag`, `stage`, `stage_changed`,
`sprite`, and axis values.

**Backends.** By default the engine talks to a local Ollama server. To generate
with the OpenAI API instead, set `LLM_BACKEND=openai` and `OPENAI_API_KEY=sk-…`
in your `.env` (see [.env.example](.env.example)). The key stays on the server.
Model, temperature, and context window are all env-configurable.

## The headline: characters that change, explainably

The moment tag is the *weather* — how the character reacts to this message. The
**stage** is the *climate* — who they are as the relationship deepens. A
character can start loud and guarded and grow calm and warm, and every shift is
caused by tracked numbers you can inspect, not by the model's mood. Want a long,
slow arc? Raise the axis ceiling with `AXIS_MAX=1000` and the same character
warms across many more messages. See [CHARACTER_PACK_SPEC.md](CHARACTER_PACK_SPEC.md).

See it in action: [docs/EXAMPLE_RUN.md](docs/EXAMPLE_RUN.md) walks through a real
100-message conversation on `gemma3:12b` — the stage climb, memory recall,
boundaries, and web lookup, quoted verbatim.

## Optional features (env toggles)

All off/local by default; see [.env.example](.env.example).

- **Persistent sessions** — relationship state and transcripts are saved under
  `.local/sessions`, so a long correspondence resumes across restarts.
- **Non-roleplay mode** (`NON_RP=true`) — the character keeps its voice but
  stops narrating actions (`*smiles*`, stage directions) and answers like a
  plain pet-assistant. Good for coding help and for showing the mechanics.
- **Non-romance mode** (`NON_ROMANCE=true`) — the relationship stays strictly
  platonic however close it grows; warmth and friendship still deepen, but
  flirtation and romance are declined and romantic advances are gently
  redirected. Independent of `NON_RP` — enable either, both, or neither.
- **Reply language** (`LANGUAGE=Russian`, or a per-request `language` field, or
  the web-UI dropdown) — the character answers in that language whatever the
  user writes in. Empty = it matches the user's own language.
- **User gender** (`USER_GENDER=male|female`, per-request `user_gender`, or the
  web-UI dropdown) — tells the character how to address the user, so pronouns
  and agreement come out right in gendered languages (Russian, etc.).
- **Web lookup** (`WEB_SEARCH=true`) — when a pack declares a `web_lookup` tag
  and the classifier picks it, the engine runs a DuckDuckGo search and grounds
  the reply on the snippets. Off by default (it enables outbound network).

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

## Development

```bash
make check      # ruff + pytest (the gate before every commit)
make help       # list all targets

# Drive a scripted conversation through a character on a live Ollama model:
make scenario ARGS="--character kaguya --length showcase --memory --web-search"
```

Scenario lengths: `10 | 20 | 30 | coding | boundary | showcase`; seed a specific
relationship level with `--affection/--trust/--bond`. See
[docs/EXAMPLE_RUN.md](docs/EXAMPLE_RUN.md) for an annotated run.

## Contributing

Code PRs are not merged — the engine is author-driven (fork freely, it's
Apache-2.0). The community contribution is **characters**. See
[CONTRIBUTING.md](CONTRIBUTING.md) and [SUBMISSION_TERMS.md](SUBMISSION_TERMS.md).

## License

Engine code: **Apache-2.0**. Sample character *content* is licensed separately —
each pack under `characters/` has its own README and `meta.license`.

> Work in progress — v0.1. Expect rough edges.
