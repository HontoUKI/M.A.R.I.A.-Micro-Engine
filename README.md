# M.A.R.I.A. Micro-Engine

A lightweight, character-pack driven chat engine with an OpenAI-compatible API.

- **Engine** (`engine/`) — generic character runtime: YAML character packs,
  three relationship axes (affection / trust / bond) moved by an explicit
  delta table, prompt assembly from named fragments. No character is built in:
  without a pack the engine honestly reports that nothing is loaded.
- **App** (`app/`) — thin FastAPI layer exposing an OpenAI-compatible API, so
  existing OpenAI clients can talk to a character by pointing at this server.

## Quickstart

```bash
pip install -r requirements.txt
ollama pull gemma3:12b        # the default chat model (any Ollama model works)
uvicorn app.main:app          # serves the API and the web shell on :8000
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

Build your own character: see [CHARACTER_PACK_SPEC.md](CHARACTER_PACK_SPEC.md)
and the packs under [characters/](characters/). For a slow burn, set
`AXIS_MAX=1000`.

> Work in progress — v0.1. Expect rough edges.

License: Apache-2.0. Sample character *content* is licensed separately — see
each pack's README.
