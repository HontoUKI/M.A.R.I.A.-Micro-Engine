# Character Pack Specification — v1

A **character pack** is the data that turns the generic Micro-Engine into a
specific character. The engine ships no built-in character: everything a
character is — how it talks, how it feels, how it reacts — lives in a pack.

This document is the stable public contract. The schema is versioned with
semver (`spec_version`); breaking it breaks every published character, so it
changes rarely and deliberately.

> Scope of the community tier: the engine perceives a turn by asking the LLM
> to pick **one** moment tag from the pack's closed list, then moves three
> numeric axes by a fixed table you define. There is no ML brain and no
> file/command access. A pack is prompt-and-number data, not code.
>
> The headline capability is that a character **changes explainably over time**:
> as affection and trust grow, the pack shifts through named relationship
> **stages** (§2.12), and each shift is caused by tracked state you can inspect,
> not by the model's whim. The moment tag is the weather; the stage is the
> climate.

---

## 1. Layout on disk

A pack is a directory:

```
my-character/
├── pack.yaml          # the whole character, except binary art
└── sprites/           # image files referenced by pack.yaml
    ├── idle.png
    ├── happy.png
    └── annoyed.png
```

`pack.yaml` is parsed with a safe YAML loader (no custom tags, no object
construction). Sprites are referenced by **bare filename** and must live
inside `sprites/`.

---

## 2. `pack.yaml` fields

### 2.1 `spec_version` (required, int)

The pack schema major version this pack targets. The engine loads a pack only
when `spec_version` matches the engine's supported major (`1`). A mismatch is
rejected with a clear error rather than guessed at.

### 2.2 `meta` (required)

| Field          | Req | Type   | Notes |
|----------------|-----|--------|-------|
| `name`         | ✅  | string | Unique id, `^[a-z0-9][a-z0-9_-]*$`. This is the OpenAI `model` name clients request. |
| `display_name` | ✅  | string | Human-facing name. |
| `version`      | ✅  | string | Pack version, semver (`MAJOR.MINOR.PATCH`). |
| `license`      | ✅  | string | Content license of this character (e.g. `CC-BY-4.0`). |
| `author`       | ✅  | string | Who made the pack. |
| `fallback_tag` | ✅  | string | Id of the tag used when classification fails or is invalid (see §5). Must exist in `tags`. |
| `description`  |     | string | One-line summary for the gallery. |

### 2.3 `identity` (required, string)

The character's identity skeleton. This becomes the **pinned prefix** of every
prompt (§ engine: two-segment assembly) — sent once, cached, never re-injected.
Keep it a compact "who you are", not a rulebook: base tone, voice, disposition.

### 2.4 `axes` (optional)

The starting value (in points) of each relationship axis. The floor is always
`0`; the ceiling is the runtime `AXIS_MAX` (default `100`), not a pack field.
So a pack only chooses where the character begins; omitted axes start at `0`.

```yaml
axes:
  affection: {start: 20}
  trust:     {start: 15}
  bond:      {start: 0}
```

`AXIS_MAX` is a **deployment knob for slow-burn**, not part of the character.
Raise it (e.g. to `1000`) and the same per-turn deltas become a smaller
fraction of the whole, so relationships warm far more slowly across many more
messages. Stage thresholds (§2.12) are ratios, so they need no retuning when
you change it.

### 2.5 `tags` (required, list)

The closed enum of **moment tags** the LLM classifier chooses from. Each tag is
one holistic read of the current turn.

```yaml
tags:
  - id: warmth
    description: "The user is warm, friendly, playful, or affectionate."
    sentiment: positive
  - id: hostility
    description: "The user is rude, dismissive, hostile, or insulting."
    sentiment: negative
  - id: neutral
    description: "Ordinary exchange; nothing that should move the relationship."
    sentiment: neutral
```

| Field         | Req | Notes |
|---------------|-----|-------|
| `id`          | ✅  | `^[a-z0-9][a-z0-9_-]*$`, unique within the pack. |
| `description` | ✅  | Written **for the LLM**: it decides tag selection. Be concrete. |
| `sentiment`   |     | `positive` \| `negative` \| `neutral`. Advisory; used for balance checks. |

Limits: **2–32 tags**. At least **one** tag with `sentiment: negative` (a
character that can only warm up ratchets into sycophancy — see §6).

**Reserved tag `web_lookup`.** If a pack declares a tag with id `web_lookup`
and the deployment sets `WEB_SEARCH=true`, a turn the classifier assigns to
that tag triggers a DuckDuckGo search; the result snippets are handed to the
voicing model as grounding. Without `WEB_SEARCH` it behaves like any other tag
(no network). Give it a neutral delta and a block that says to answer from the
provided results in-character.

### 2.6 `deltas` (required, map)

For every tag id, the vector applied to the axes when that tag is chosen.

```yaml
deltas:
  warmth:    {affection: 2.0, trust: 1.0, bond: 0.2}
  hostility: {affection: -3.0, trust: -2.0, bond: -0.1}
  neutral:   {affection: 0.0, trust: 0.0, bond: 0.0}
```

- Every tag **must** have a delta; every delta key **must** be a known tag.
- The LLM never sees or writes these numbers — the engine applies them.
- **Bond is the slow axis:** for each tag, `|bond|` must be `<=` both
  `|affection|` and `|trust|` (or all three zero). The engine rejects packs
  that violate this so bond stays a long-horizon signal.

### 2.7 `blocks` (required, map)

For every tag id, the steering block injected into the **dynamic tail** for the
turn that tag was chosen. This is the per-turn "how to respond right now" nudge.
An empty string is allowed (no extra steering).

```yaml
blocks:
  warmth:    "Let the warmth land. Be a little more open than usual."
  hostility: "Hold a calm, guarded boundary. Do not grovel or escalate."
  neutral:   ""
```

Every tag must have a block entry. Block text is length-limited (§4) and
scanned for prompt-injection patterns (§4).

### 2.8 `sprites` (optional, map)

State → sprite filename (relative to `sprites/`). `default` is required if the
map is present. Keys may be tag ids or the literal `default`.

```yaml
sprites:
  default:   idle.png
  warmth:    happy.png
  hostility: annoyed.png
```

Filenames must be bare (no `/`, no `..`, no absolute paths) and resolve to an
existing file inside `sprites/`. Allowed extensions: `.png .jpg .jpeg .webp`.

### 2.9 `decay` (optional, map)

Per-idle-step pull of each axis back toward its baseline. Prevents a positive
ratchet (LLMs drift agreeable). Defaults to a small pull if omitted.

```yaml
decay:
  affection: 0.5
  trust:     0.3
  bond:      0.05
```

### 2.10 `invariants` (optional, list of strings)

Extra rules pinned into the prefix alongside `identity`. Length-limited and
injection-scanned like blocks.

### 2.11 `reply_directive` (optional, string)

A short reminder injected into the **dynamic tail**, right next to the user
message, on **every** turn (after the stage and tag blocks). Because a small
model heeds a nearby nudge far better than a rule buried in the far-away pinned
prefix, this is the place for a firm per-turn instruction the character keeps
drifting away from — most often **brevity** ("keep it to 2–3 sentences") or a
persistent stylistic tic to suppress. Leave it empty when the `invariants`
already hold. Length-limited (≤ 1000 chars) and injection-scanned like an
invariant.

### 2.12 `actions` (optional, list of strings)

Cosmetic action whitelist (e.g. `emote`, `change_scene`). Advisory metadata for
clients; the engine performs no file, command, or network action on their
behalf. There is deliberately **no** safe-chain in this tier.

### 2.13 `stages` (optional, map) — the headline feature

Relationship stages give a character a **slow, explainable arc**. The engine
derives the current stage from the **affection+trust ratio** and injects the
matching tone into the turn's dynamic tail, on top of the moment tag's block.
Where a tag reacts to *this message*, a stage expresses *how close you two have
become*.

Stages are **author-defined**: you choose how many, what to call them, and
where they begin. Each stage is a `{id, up_to, block}` entry; the engine
activates the first stage whose `up_to` threshold covers the current closeness
ratio (the last stage is the catch-all).

```yaml
stages:
  - id: strangers
    up_to: 0.15
    block: "You barely know them. Guarded and distant."
  - id: acquaintances
    up_to: 0.45
    block: "Warming a little; the guard eases."
  - id: friends
    up_to: 0.8
    block: "At ease; openly warm."
  - id: close
    up_to: 1.0
    block: "Fully unguarded and sincere."
```

| Field   | Req | Notes |
|---------|-----|-------|
| `id`    | ✅  | `^[a-z0-9][a-z0-9_-]*$`, unique within the pack. Reported to clients. |
| `up_to` | ✅  | Ratio threshold in `(0, 1]`. Thresholds must be strictly ascending; make the last one `1.0` to cover the top. |
| `block` |     | Tone text for this stage; length-limited and injection-scanned like a block (§4). |

The **closeness ratio** is `(affection + trust) / 2`, each divided by
`AXIS_MAX`. Bond, the slow long-term axis, does not gate the acted stage.
Because thresholds are ratios (not raw points), they need no retuning when a
deployment changes `AXIS_MAX` for slow-burn. Up to 32 stages.

Every chat response reports the active `stage` (its id, or `null` when a pack
defines no stages) and whether this turn crossed into it (`stage_changed`) in
the `x_micro_engine` extension, so a client can show *why* the character
shifted.

---

## 3. A minimal valid pack

```yaml
spec_version: 1
meta:
  name: aria
  display_name: Aria
  version: 0.1.0
  license: CC-BY-4.0
  author: example
  fallback_tag: neutral
identity: |
  You are Aria, a calm librarian who speaks softly and remembers everything.
tags:
  - {id: warmth,    description: "The user is warm or friendly.", sentiment: positive}
  - {id: hostility, description: "The user is rude or hostile.",   sentiment: negative}
  - {id: neutral,   description: "Ordinary exchange.",            sentiment: neutral}
deltas:
  warmth:    {affection: 2.0, trust: 1.0, bond: 0.2}
  hostility: {affection: -3.0, trust: -2.0, bond: -0.1}
  neutral:   {affection: 0.0, trust: 0.0, bond: 0.0}
blocks:
  warmth:    "Let the warmth land; be a touch more open."
  hostility: "Stay calm and guarded; do not grovel."
  neutral:   ""
```

---

## 4. Safety limits (enforced by the loader)

A pack is executable-as-prompt data from an untrusted author, so the loader
enforces hard limits and rejects anything outside them:

| Limit                     | Value |
|---------------------------|-------|
| `pack.yaml` size          | ≤ 256 KiB |
| `identity` length         | ≤ 4000 chars |
| single block length       | ≤ 2000 chars |
| single invariant length   | ≤ 1000 chars |
| `reply_directive` length  | ≤ 1000 chars |
| number of tags            | 2–32 |
| number of sprites         | ≤ 64 |
| sprite file size          | ≤ 4 MiB each |

Text in `identity`, `blocks`, `invariants`, `stages`, and `reply_directive`
is scanned for prompt-injection
/ system-override patterns (e.g. "ignore previous instructions", "you are now",
"system prompt:", role-hijack markers). A match rejects the pack. This is
defense-in-depth, not a substitute for human review of gallery submissions.

---

## 5. How the engine uses a pack (informative)

1. **Session start** — `identity` + `invariants` are assembled once into the
   pinned prefix.
2. **Each turn** — the LLM is asked to pick one tag `id` from `tags`
   (constrained decode). An invalid or missing choice retries once, then falls
   back to `meta.fallback_tag`.
3. The engine applies `deltas[tag]` to the axes (clamped to bounds; bond moves
   slowly), then resolves the current relationship **stage** from the new
   axes (§2.13). Both the tag's block and the active stage's block are injected
   into the dynamic tail, followed by `reply_directive` (§2.11) when set.
4. A second LLM call voices the reply. The response reports `tag`, `stage`,
   `stage_changed`, `sprite`, and the axis values.
5. On idle, `decay` pulls the axes toward baseline (which can lower the stage
   again — arcs can go backwards).

## 6. Balance guidance (informative)

- Include real negative tags; a character that only ever warms up is a
  sycophant. The loader enforces at least one negative tag.
- Keep bond deltas small — bond is the months-long axis, not the per-message
  one. The loader enforces `|bond| <= |affection|, |trust|` per tag.
- Set `decay` so a quiet conversation drifts back toward baseline instead of
  freezing at a peak.

---

## 7. Versioning

`spec_version` is the **schema** major version (this document). `meta.version`
is **your pack's** version. The engine supports `spec_version: 1`. When the
schema gains a breaking change it becomes `2`, and v1 packs keep loading on v1
engines. Additive, backward-compatible fields do not bump the major.
