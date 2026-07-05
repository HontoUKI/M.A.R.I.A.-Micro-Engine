"""Every character pack shipped in `characters/` must load and validate.

Guards the sample packs against silent drift when the loader or schema
changes. Uses the repo's real characters directory (not the per-test tmp cwd).
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from engine.character import CharacterRuntime
from engine.pack import load_pack

_CHARACTERS_DIR = Path(__file__).resolve().parents[1] / "characters"


def _sample_dirs() -> list[str]:
    if not _CHARACTERS_DIR.is_dir():
        return []
    return [
        str(_CHARACTERS_DIR / name)
        for name in sorted(os.listdir(_CHARACTERS_DIR))
        if (_CHARACTERS_DIR / name / "pack.yaml").is_file()
    ]


@pytest.mark.parametrize("pack_dir", _sample_dirs())
def test_shipped_pack_loads_and_validates(pack_dir):
    pack = load_pack(pack_dir)
    # Cross-references the loader guarantees, restated as a smoke check.
    tag_ids = {t.id for t in pack.tags}
    assert pack.meta.fallback_tag in tag_ids
    assert set(pack.deltas) == tag_ids
    assert set(pack.blocks) == tag_ids


def test_megumin_sample_is_present_and_shaped():
    pack = load_pack(str(_CHARACTERS_DIR / "megumin"))
    assert pack.meta.name == "megumin"
    assert len(pack.tags) == 9
    assert pack.tag("insult").sentiment == "negative"
    assert pack.tag("intimacy_push").sentiment == "negative"
    # Bond stays the slow axis on her biggest positive swing.
    warmth = pack.deltas["warmth"]
    assert abs(warmth.bond) <= abs(warmth.affection)


class _StubLLM:
    """Picks a fixed tag for the classifier, returns a canned voice reply."""

    def __init__(self, tag, reply):
        self._tag = tag
        self._reply = reply

    def chat(self, messages, *, model=None, fmt=None, options=None):
        return json.dumps({"tag": self._tag}) if fmt is not None else self._reply


def test_kaguya_sample_is_serious_and_more_guarded_than_megumin():
    kaguya = load_pack(str(_CHARACTERS_DIR / "kaguya"))
    megumin = load_pack(str(_CHARACTERS_DIR / "megumin"))
    assert kaguya.meta.name == "kaguya"
    assert len(kaguya.tags) == 10
    assert kaguya.tag("provocation").sentiment == "negative"
    # The contrast the two packs exist to prove: Kaguya starts more guarded.
    assert kaguya.axes.affection.start < megumin.axes.affection.start
    assert kaguya.axes.trust.start < megumin.axes.trust.start


@pytest.mark.parametrize("name", ["megumin", "kaguya"])
def test_samples_define_a_valid_author_stage_ladder(name):
    pack = load_pack(str(_CHARACTERS_DIR / name))
    # Showcases for explainable change: several stages, ascending, covering the top.
    assert len(pack.stages) >= 3
    ups = [s.up_to for s in pack.stages]
    assert ups == sorted(ups)
    assert pack.stages[-1].up_to == 1.0


def test_alex_sample_is_original_and_grumbles_via_shared_frustration():
    alex = load_pack(str(_CHARACTERS_DIR / "alex"))
    assert alex.meta.name == "alex"
    # An original character, not a fan work — no third-party IP.
    assert "Original" in alex.meta.license
    # The arc that defines him: polished professional -> openly grumbly.
    stage_ids = [s.id for s in alex.stages]
    assert stage_ids == ["professional", "warming", "candid", "unfiltered"]
    # Venting together is his strongest trust-builder — more than any praise.
    assert alex.deltas["shared_frustration"].trust >= alex.deltas["recognition"].trust
    assert alex.deltas["shared_frustration"].trust >= alex.deltas["rapport"].trust


def test_samples_use_distinct_stage_names():
    # The whole point of author-defined stages: the two packs name them differently.
    megumin = {s.id for s in load_pack(str(_CHARACTERS_DIR / "megumin")).stages}
    kaguya = {s.id for s in load_pack(str(_CHARACTERS_DIR / "kaguya")).stages}
    assert megumin.isdisjoint(kaguya)


def test_megumin_pack_drives_a_full_runtime_turn():
    pack = load_pack(str(_CHARACTERS_DIR / "megumin"))
    llm = _StubLLM("explosion_praise", "BEHOLD, my devotion to EXPLOSION!")
    result = CharacterRuntime(pack, llm).respond("your explosion magic is incredible")
    assert result.tag == "explosion_praise"
    assert result.reply.startswith("BEHOLD")
    # explosion_praise delta (+5 / +3 / +0.4) over her 12 / 8 / 0 baseline.
    assert result.axes.affection == 17
    assert result.axes.trust == 11
