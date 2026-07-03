# Kaguya Shinomiya — sample character pack

A second demonstration pack, built as a deliberate contrast to Megumin. Where
Megumin opens loud and theatrical and softens as she grows close, Kaguya is
composed and serious from the very first word — she starts guarded (low
affection and trust) and only rarely, slowly, lets her poise slip. Two packs
this different sharing one engine is the point: the personality is entirely in
the data.

## Provenance and licensing

- **Kaguya and *Kaguya-sama: Love Is War* are © Aka Akasaka / SHUEISHA.** This
  pack is an unofficial, non-commercial fan work included purely to demonstrate
  the engine. It is not affiliated with or endorsed by the rights holders.
- **No character art is bundled.** The `sprites` map is intentionally empty. To
  use sprites locally, add image files under `sprites/` and map them in
  `pack.yaml` (see `CHARACTER_PACK_SPEC.md`), using art you own or that is
  licensed for the purpose.

The engine code is Apache-2.0; this sample's *content* is not (see above).

## Try it

```bash
uvicorn app.main:app
# then, against the OpenAI-compatible endpoint:
#   model: "kaguya"
```
