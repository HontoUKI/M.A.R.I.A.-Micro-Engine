# Gallery

Characters for the Micro-Engine come in two tiers. This keeps the maintainer
from having to vouch for *everything* while still giving newcomers a safe,
curated starting set.

## Approved

Packs the author has personally reviewed for safety and IP and is willing to
host and recommend. The reference examples of this tier ship in the repo under
[`characters/`](../characters/) — load them straight away with the
[quickstart](../README.md).

To get a pack into this tier, submit it (see
[CONTRIBUTING.md](../CONTRIBUTING.md)); it is reviewed against the checklist
there and the [submission terms](../SUBMISSION_TERMS.md).

## Community (unverified)

Everything else. The engine is Apache-2.0 and packs are just data, so anyone
can **fork, build, and share** characters without asking. These are **not
reviewed and not endorsed** — treat an unverified pack like any file from a
stranger: read its `pack.yaml` before you run it. The loader blocks the obvious
attacks, but a human should still glance at the prompt text.

## Not a hosting service (yet)

For v0.1 the "gallery" is this curation model plus the bundled approved
samples — not a website or a pack index. A browsable gallery may come later;
until then, discovery happens through forks and submitted links.
