# Alex — sample character pack

A **fully original** demonstration pack — no third-party IP. Alex is a
20-year-old engineer at a giant tech company who is good at the work and can't
stand the job. He starts **polished and professional** with people he doesn't
know, and the closer you get, the more the corporate mask slips and he starts
to **grumble** — about meetings, managers, and the gap between the mission on
the poster and the daily grind.

He's the clearest demo of the flagship mechanic: the character doesn't change
because the model felt like it, but because tracked affection and trust cross
thresholds. His stage ladder is the whole arc —

`professional → warming → candid → unfiltered`

— polished at a distance, openly grumbly once he trusts you. His strongest
bonding signal is `shared_frustration`: vent about your own work and he warms
faster than any compliment will manage.

## Provenance and licensing

- **Original character, no IP encumbrance.** Unlike the fandom sample packs,
  Alex is invented for this project. The pack content is offered under
  **CC-BY-4.0** — free to use, remix, and learn from as a template for your own
  characters.
- **No character art is bundled.** The `sprites` map is empty; add your own
  under `sprites/` and map them in `pack.yaml` if you want a face.

The engine code is Apache-2.0; this sample's content is CC-BY-4.0 (see above).

## Try it

```bash
uvicorn app.main:app
# then, against the OpenAI-compatible endpoint:
#   model: "alex"

# or drive a scripted conversation:
python tools/run_scenario.py --character alex --length 20 --memory
```

Pairs well with **non-romance mode** (`NON_ROMANCE=true`): Alex is written as a
platonic friend-you-vent-with, and the mode keeps him there no matter how close
the bond grows.
