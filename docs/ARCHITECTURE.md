# Architecture

Two layers, one direction of dependency:

```
app/     — FastAPI shell, OpenAI-compatible wire contracts. No character logic.
engine/  — generic character runtime. No HTTP concerns.
```

- **Character pack** — versioned YAML data (identity, tag enum, delta table,
  prompt blocks, sprites). The engine is character-neutral: no pack loaded →
  it says so instead of improvising a personality.
- **State axes** — `affection | trust | bond`, moved only by the engine from
  an explicit per-tag delta table. The LLM never reads or writes the numbers.
- **Perception loop** — one LLM call classifies the moment into a single tag
  from the pack's closed enum; the engine applies the delta; the prompt
  manager assembles the next prompt; a second LLM call voices the reply.
- **Prompt layout** — two segments: a stable session prefix (pack identity,
  pinned once) and a per-turn tail (state mood + steering blocks) that rides
  with the user message and never accumulates in history.

Full write-up lands with v0.1.
