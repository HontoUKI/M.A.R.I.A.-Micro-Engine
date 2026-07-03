# M.A.R.I.A. Micro-Engine

A lightweight, character-pack driven chat engine with an OpenAI-compatible API.

- **Engine** (`engine/`) — generic character runtime: YAML character packs,
  three relationship axes (affection / trust / bond) moved by an explicit
  delta table, prompt assembly from named fragments. No character is built in:
  without a pack the engine honestly reports that nothing is loaded.
- **App** (`app/`) — thin FastAPI layer exposing an OpenAI-compatible API, so
  existing OpenAI clients can talk to a character by pointing at this server.

> Work in progress — v0.1 is under construction. The quickstart and the
> character pack guide will land with the first release.

License: Apache-2.0.
