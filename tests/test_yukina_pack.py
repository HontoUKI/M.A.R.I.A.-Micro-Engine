"""Yukina: attachment unlocks what she does not have before it.

The pack rests on one claim, and it is not about prose: possessiveness, jealousy and
guardianship live in a WINDOW of closeness, and outside the window the engine does not show
the tag to the classifier at all. So this is not "we asked the model not to be jealous too
early" — there is nothing to choose.

Exactly this is checked, from both sides (R27): that a locked tag is not in the offered
list, and that a model that names it anyway gets the fallback. The first is about the
shop window, the second about the guarantee, and they need not coincide.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.pack import load_pack
from engine.perception import TagClassifier, _available_tags

_YUKINA = Path(__file__).resolve().parents[1] / "characters" / "yukina"

# Stages at which the gates open — by BOND, not by mood (09.09). Kept here so that changing a
# number in the pack shows up as changing a claim, not as behaviour that silently
# drifted.
ATTACHED = 0.15   # he left, he came back, he is in danger
JEALOUS = 0.30    # someone else
KEEPING = 0.50    # reciprocity, and "leave me alone" as something she does not accept

LOCKED_EARLY = {"he_left", "he_came_back", "he_is_in_danger", "someone_else",
                "told_to_back_off", "intimacy_return"}


@pytest.fixture
def pack():
    return load_pack(str(_YUKINA))


class _Insists:
    """A model that names the same tag whatever it is offered."""

    def __init__(self, tag: str) -> None:
        self._tag = tag

    def chat(self, messages, *, model=None, fmt=None, options=None):
        return json.dumps({"tag": self._tag})


def test_pack_is_the_yandere_rework(pack):
    assert pack.meta.name == "yukina"
    # The ladder hangs on BOND: a bad evening spoils the mood and does not turn the arc back.
    assert pack.stage_axis == "bond"
    assert [s.id for s in pack.stages] == [
        "wary", "helping", "attached", "keeping", "sabotage", "obsessed",
    ]
    # The gates stand on stage borders: otherwise "she became different" and "something
    # different became available to her" would happen at different moments.
    assert pack.tag("he_is_in_danger").unlock_at == ATTACHED
    assert pack.tag("someone_else").unlock_at == JEALOUS
    assert pack.tag("he_left").unlock_at == ATTACHED
    # Leaving and coming back are one gate: noticing only half would mean he leaves
    # forever.
    assert pack.tag("he_came_back").unlock_at == pack.tag("he_left").unlock_at
    assert pack.tag("intimacy_return").unlock_at == KEEPING
    assert pack.tag("told_to_back_off").unlock_at == KEEPING
    # Refusal and reciprocity are one gate from two sides, with no gap between them.
    assert pack.tag("intimacy_push").lock_at == pack.tag("intimacy_return").unlock_at


def test_the_gate_edges_are_inclusive_on_both_sides(pack):
    """What happens EXACTLY on the threshold, not next to it.

    A window is checked as `unlock_at <= ratio <= lock_at`, so both bounds are inclusive, and
    at the 0.7 mark itself both refusal and reciprocity are available at once. This is neither
    a defect nor a design — it is a consequence, and it is recorded here so that changing the
    comparison in the engine fails a test instead of surfacing in the game as one strange turn.
    """
    at = lambda r: {t.id for t in _available_tags(pack, r)}  # noqa: E731
    assert "he_is_in_danger" in at(ATTACHED)          # opens AT the threshold
    assert "he_is_in_danger" not in at(ATTACHED - 0.01)
    assert {"intimacy_push", "intimacy_return"} <= at(KEEPING)
    assert "intimacy_push" not in at(KEEPING + 0.001)  # and closes right past it


def test_a_stranger_is_not_offered_the_possessive_reads(pack):
    offered = {t.id for t in _available_tags(pack, ratio=0.02)}
    assert offered.isdisjoint(LOCKED_EARLY)
    # And the ordinary ones are in place: the pack does not get poorer, it gets different.
    assert {"gift", "watched", "neglect", "intimacy_push"} <= offered


def test_once_she_is_attached_the_guarding_reads_appear(pack):
    offered = {t.id for t in _available_tags(pack, ratio=JEALOUS)}
    assert {"he_left", "he_came_back", "he_is_in_danger", "someone_else"} <= offered
    # But not all at once: the upper gates are still closed.
    assert "intimacy_return" not in offered
    assert "told_to_back_off" not in offered


def test_at_the_top_the_romance_gate_flips(pack):
    offered = {t.id for t in _available_tags(pack, ratio=0.75)}
    assert "intimacy_return" in offered
    assert "told_to_back_off" in offered
    # Refusing courtship stops existing exactly where the answer to it appears.
    assert "intimacy_push" not in offered


def test_a_locked_tag_cannot_be_chosen_even_when_the_model_names_it(pack):
    """The guarantee, not the shop window.

    The list is what the model sees; what must be checked is what it can GET. A model that
    named a locked tag must go to the fallback, otherwise the whole gate rests on its
    obedience.
    """
    chosen = TagClassifier(_Insists("someone_else")).classify(
        pack, "who were you with", ratio=0.05
    )
    assert chosen == pack.meta.fallback_tag
    # And the very same model answer above the gate passes — otherwise the test would prove
    # a broken classifier, not a working gate.
    assert TagClassifier(_Insists("someone_else")).classify(
        pack, "who were you with", ratio=0.8
    ) == "someone_else"


def test_a_gift_is_the_single_biggest_thing_he_can_do(pack):
    """Diamonds are a girl's best friend — as a number, not as a line."""
    gift = pack.deltas["gift"]
    others = [d.affection for tag, d in pack.deltas.items() if tag != "gift"]
    assert gift.affection > max(others)
    assert abs(gift.bond) <= min(abs(gift.affection), abs(gift.trust))


def test_leaving_her_makes_her_cling_and_trust_less(pack):
    """Leaving does not cool — it thickens.

    The only row in the table where the axes go in DIFFERENT directions: she pulls harder and
    relies less. Closeness must fall meanwhile, otherwise disappearing would be a road
    upward.
    """
    left = pack.deltas["he_left"]
    assert left.affection > 0
    assert left.trust < 0
    assert left.affection + left.trust < 0


def test_danger_around_him_moves_nothing(pack):
    """Danger is a state of affairs, not his deed.

    The same rule that fixed `on_your_own` on 08.09: the relationship is moved by what HE did.
    Otherwise a night outside would read as his contribution to their closeness.
    """
    danger = pack.deltas["he_is_in_danger"]
    assert (danger.affection, danger.trust, danger.bond) == (0.0, 0.0, 0.0)


def test_coming_back_restores_and_does_not_pay(pack):
    """Leaving and coming back is not a road upward.

    Otherwise she would have a way of gaining closeness that the player uses doing nothing: step
    away for a minute and come back. Over a full circle trust must stay negative — it is
    exactly what leaving spends.
    """
    left, back = pack.deltas["he_left"], pack.deltas["he_came_back"]
    assert back.affection > 0 and back.trust > 0
    assert left.trust + back.trust < 0
    assert back.affection < pack.deltas["gift"].affection


def test_being_killed_by_him_costs_the_stages_he_built(pack):
    """Killing her is expensive, and the price is written as a number, not a promise.

    Trust is exactly what this destroys: minus eight, while the biggest positive move gives
    four. Stages gained over an evening crumble. Attachment meanwhile holds almost
    entirely — that is the whole trope.
    """
    killed = pack.deltas["killed_by_him"]
    assert killed.trust <= -2 * pack.deltas["gift"].trust
    assert killed.affection > killed.trust
    assert abs(killed.bond) <= min(abs(killed.affection), abs(killed.trust))


def test_dying_to_the_world_moves_nothing(pack):
    """A creeper is not his deed.

    The same rule as for `on_your_own` and `he_is_in_danger`: the relationship is moved by what
    HE did. Otherwise a bad jump would read as his contribution.
    """
    died = pack.deltas["died"]
    assert (died.affection, died.trust, died.bond) == (0.0, 0.0, 0.0)


def test_neither_death_is_gated(pack):
    """One can die by his hand on the very first evening.

    The gates hold possessiveness, not the ability to notice one's own death: a tag open only
    to the close ones would leave a stranger without words exactly where speaking matters
    most.
    """
    early = {t.id for t in _available_tags(pack, ratio=0.01)}
    assert {"killed_by_him", "died"} <= early


def test_wanting_things_is_a_moment_and_not_the_character(pack):
    """The author's note 09.09: "with constant requests she looks more like a pirate".

    The gift count stood in `identity`, that is it sounded EVERY turn regardless of the
    occasion — and she begged for things in every line. This trait's place is in the occasion
    that is about a gift, and in the hint next to the message.
    """
    assert "keep score" not in pack.identity
    assert "diamond" not in pack.identity.lower()
    # And where the occasion really is about a gift, it stayed in full.
    assert "diamond" in pack.blocks["gift"].lower()
    assert pack.reply_directive, "a near hint is stronger than a distant rule"
    assert "attention" in pack.reply_directive.lower()


def test_the_dossier_is_weighed_on_every_turn_not_only_when_insulted(pack):
    """A fact named and a fact taken into account are different things.

    The first measurement 09.09: the dossier stood in the prompt, and behaviour did not change
    by a single line. A turn after rudeness read as `attention`, whose block tells her to beam —
    and the instruction to check the record sat only in the `insult` block, that is it fired
    only when being rude right now. It worked once it stood where EVERY turn sounds.
    """
    assert "note about what he has done" in pack.reply_directive
    # And the block about the rudeness itself knows about it too: one of the two places is not enough.
    assert "note above" in pack.blocks["insult"]


def test_every_stage_has_a_cold_face(pack):
    """A stage is a climate, and a climate must be able to be bad.

    The author's note: "she is still kind-ish to a player who behaves rudely". One of three
    causes was here: all five stages spoke only warmth, down to "you forgive him before he
    finishes the apology". Whatever he did a minute ago, the climate told her to be devoted —
    and the dossier stayed a polite caveat.

    Each stage has its OWN cold, because the distance differs: a stranger goes silent, a close
    one does not leave and stops being pleasant.
    """
    for stage in pack.stages:
        assert "unkind lately" in stage.block, f"stage {stage.id} cannot go cold"


def test_a_trinket_cannot_buy_off_an_insult(pack):
    """Live 09.09 he was rude four times and bought his way out with ONE arrow.

    Everything handed over counted as a gift, so junk returned more than an insult cost, and
    rudeness came free. Now a trinket has its own price, and it is many times less than
    the price of rudeness.
    """
    trinket, gift, insult = pack.deltas["trinket"], pack.deltas["gift"], pack.deltas["insult"]
    assert trinket.affection < gift.affection / 4
    assert trinket.affection < abs(insult.affection)
    assert trinket.trust < abs(insult.trust)


def test_rudeness_costs_more_than_the_biggest_kindness_returns(pack):
    """Otherwise the score is always in his favour, however he behaves."""
    insult, gift = pack.deltas["insult"], pack.deltas["gift"]
    assert abs(insult.trust) > gift.trust
