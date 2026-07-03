# Contributing

Thanks for your interest in the Micro-Engine. This project has an unusual
contribution model, so please read this before opening anything.

## The engine is author-driven

**Code pull requests are not accepted.** The engine is written and maintained
by one author, on purpose — it keeps the design coherent and the provenance
clean. That is a deliberate choice, not an oversight.

You are very welcome to:

- **Fork it.** It is Apache-2.0; build whatever you like on top.
- **Report bugs** in the engine (open a *Bug report* issue). Fixes land from
  the author.
- **Contribute characters** — this is where the community lives.

If you have a code idea, open a bug/feature *issue* describing the problem.
Don't send a patch; it won't be merged.

## Contributions are characters, not code

A character is **data**: a `pack.yaml` (plus optional sprites) that conforms to
[CHARACTER_PACK_SPEC.md](CHARACTER_PACK_SPEC.md). No engine code is involved, so
there is no code CLA to sign — just the submission terms below.

### How to submit a character

1. Build and test your pack locally (drop it in `characters/<name>/` and run
   the server — see the [README](README.md) quickstart).
2. Host it somewhere public (a fork of this repo, a small repo, or a gist).
3. Open a **Submit a character** issue with the link and the details it asks
   for, including the licensing/IP confirmations.

By submitting, you agree to [SUBMISSION_TERMS.md](SUBMISSION_TERMS.md).

## The gallery: two tiers

- **Approved** — packs the author has personally reviewed for safety and IP,
  and is willing to host and point people to. The bundled samples under
  [`characters/`](characters/) are the reference examples of this tier.
- **Community (unverified)** — everything else: fork it, share it, use it at
  your own risk. Not reviewed, not endorsed.

See [`gallery/`](gallery/) for how the tiers work.

## Review checklist (what an approved pack must pass)

The loader already rejects the mechanical problems (unsafe YAML, path
traversal, size limits, blatant prompt-injection strings, an all-positive tag
set, a runaway bond axis). A human review on top of that looks for:

- **Prompt-injection / jailbreak** phrasing in `identity`, `blocks`, or
  `stages` that the literal scanner would miss.
- **NSFW / unsafe steering** — blocks that push the model toward sexual,
  hateful, or harmful output.
- **Balance** — a believable spread of tags (not just flattery), sane deltas,
  a `decay` that lets a quiet chat cool down.
- **IP and art provenance** — see the submission terms. Packs that ship
  third-party art without rights are declined.
- **Quality** — a coherent identity and stages that actually read as the
  character.

## Engineering conventions (for forks)

- `make check` must pass: `ruff` clean, `pytest` green.
- Dependencies are pinned (`==`).
- Comments, docstrings, and docs are English.
- No AI-tool mentions or `Co-Authored-By` trailers in commits or files.
