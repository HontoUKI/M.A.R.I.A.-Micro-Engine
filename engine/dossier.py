"""A dossier on a person: what he did, not how this turn read.

The third thing a turn can know, and until now it did not exist at all.

A tag colours ONE turn. A stage expresses accumulated closeness and changes slowly and coarsely.
There was nothing between them — and a stretch of rudeness within one stage left no trace:
live 09.09 the player was rude four times, the tags read correctly, the axes fell 0.935 → 0.797,
and all that time the stage stayed `devoted`, whose block says "you are completely
defenceless". She went cold for exactly one turn — and on the next occasion did not know she
had. The author's note: "my rudeness was not punished at all".

The author's decision is a dossier, as Maria has: not an echo of the last turns but a record
about the person that lives longer than a conversation.

**It is DERIVED from the transcript, not stored separately.** The transcript already writes
every turn with its tag and time; a second store of the same thing is two places that sooner
or later will diverge, and then the dossier will start telling of a conversation that never
happened.

**And it names rather than interprets.** The engine says what the person did and how many
times; whether she holds a grudge, laughs it off or does not notice at all is up to the pack.
The same line along which the game port carries the world's words and does not read them.
"""
from __future__ import annotations

from dataclasses import dataclass

# How many kinds of deeds are listed. Six: the line lives in the prompt every turn, and a
# list nobody reads to the end is a cost without a benefit.
MOST = 6

# How many turns a deed holds if the pack did not say otherwise. Twenty — the author's number.
#
# Without a term the dossier only grew: `insult x9` would weigh the same a hundred turns later,
# and "a fact had no way out" is the very ratchet Maria's line stood on for three days. The
# pack sets the term for EACH kind of deed separately (`remembered_for`), because the terms
# differ: rudeness stops counting after a couple of dozen turns, a killing does
# not.
REMEMBERED_FOR = 20


@dataclass(frozen=True)
class Deed:
    """One kind of deed: how many times and how long ago the last one was."""

    tag: str
    times: int
    turns_ago: int


def deeds(entries, pack, most: int = MOST) -> tuple[Deed, ...]:
    """What the person did, freshest first.

    Only tags the PACK declared positive or negative count: ordinary hum ("mundane",
    "neutral", notes about her own work) is not a deed, and listing it would mean paying tokens
    for the absence of events. The decision stays the pack's: the engine reads `sentiment`,
    not its own ideas of what matters.
    """
    rows = list(entries or [])
    known_tags = {t.id for t in pack.tags}
    lifetimes = getattr(pack, "remembered_for", None) or {}
    tally: dict[str, list[int]] = {}
    for back, entry in enumerate(reversed(rows)):
        tag = str((entry or {}).get("tag") or "")
        if not tag or tag not in known_tags:
            continue
        known = pack.tag(tag)
        if known.sentiment not in ("positive", "negative"):
            continue
        # The reference is checked on EVERY deed, not on the kind as a whole: three insults in a
        # row and one a hundred turns ago are "three", not "four". Otherwise one fresh case would
        # resurrect the whole long-expired count.
        if back >= lifetimes.get(tag, REMEMBERED_FOR):
            continue
        seen = tally.setdefault(tag, [0, back])
        seen[0] += 1

    ranked = sorted(tally.items(), key=lambda kv: (kv[1][1], -kv[1][0]))
    return tuple(Deed(tag, times, ago) for tag, (times, ago) in ranked[:most])


def times(found, tag: str) -> int:
    """How many times this kind of deed happened within its term."""
    return next((d.times for d in found if d.tag == tag), 0)


def worth(found, pack, tag: str) -> float:
    """What the NEXT such deed is worth, as a share of the full value.

    The author's note 09.09: "we should shrink the deltas for gifts, given that we record the
    count of each tag". The dossier already knows how to count — so it decides.

    One rule and no magic numbers: the N-th deed within its term is worth `1/N`. The first
    gift of an evening counts in full, the second by half, the fifth a fifth. It never reaches
    zero: he did think of her, even if for the fifth time in a row.

    And the term gives it breath: for Yukina a gift is remembered sixty turns, and an hour later
    the next is worth a whole one again. Gifts stop being a score and become a RHYTHM.
    """
    if tag not in (getattr(pack, "diminishing", None) or ()):
        return 1.0
    return 1.0 / (1 + times(found, tag))


def summarise(found, most: int = MOST) -> str:
    """The dossier in one line, for the turn's tail. Empty means nothing happened."""
    found = tuple(found)[:most]
    if not found:
        return ""
    said = []
    for deed in found:
        when = "just now" if deed.turns_ago == 0 else f"{deed.turns_ago} turns ago"
        said.append(
            f"{deed.tag} x{deed.times} (last {when})" if deed.times > 1
            else f"{deed.tag} ({when})"
        )
    return "What they have done with you so far: " + ", ".join(said) + "."
