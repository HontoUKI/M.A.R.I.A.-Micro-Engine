# Megumin — sample character pack

A demonstration pack for the M.A.R.I.A. Micro-Engine: a theatrical arch-wizard
obsessed with Explosion magic. It exercises a rich, opinionated character —
seven moment tags, a genuine tsundere dynamic (teasing vs. insult), and a
strong pinned identity — to show the engine is character-neutral and the whole
personality lives in data.

## Provenance and licensing

- **Megumin and KonoSuba are © Natsume Akatsuki / KADOKAWA.** This pack is an
  unofficial, non-commercial fan work included purely to demonstrate the
  engine. It is not affiliated with or endorsed by the rights holders.
- **No character art is bundled.** The `sprites` map is intentionally empty to
  avoid shipping third-party artwork. To use sprites locally, add image files
  under `sprites/` and map them in `pack.yaml` (see `CHARACTER_PACK_SPEC.md`),
  using art you own or that is licensed for the purpose.

The engine code is Apache-2.0; this sample's *content* is not (see above). Keep
that distinction in mind before redistributing.

## Try it

```bash
uvicorn app.main:app
# then, against the OpenAI-compatible endpoint:
#   model: "megumin"
```
