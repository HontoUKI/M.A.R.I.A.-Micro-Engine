"""Prompt fragment / recipe primitive contracts.

Pins the behavior of `engine/prompts/registry.py`. Pack-driven fragment
loading gets its own tests once the character-pack loader lands.
"""
from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from engine.prompts import (
    DuplicateFragmentError,
    Fragment,
    FragmentRegistry,
    MissingFragmentError,
    Recipe,
    assemble,
)

# ---------------------------------------------------------------- Fragment


def test_fragment_is_frozen_dataclass():
    f = Fragment(id="x", text="rule")
    with pytest.raises(FrozenInstanceError):
        f.text = "other"  # type: ignore[misc]


def test_fragment_id_must_be_nonempty_string():
    with pytest.raises(ValueError):
        Fragment(id="", text="rule")
    with pytest.raises(ValueError):
        Fragment(id=None, text="rule")  # type: ignore[arg-type]


def test_fragment_text_must_be_string():
    with pytest.raises(ValueError):
        Fragment(id="x", text=123)  # type: ignore[arg-type]


# ---------------------------------------------------------------- Registry


def test_registry_register_and_get():
    reg = FragmentRegistry()
    f = Fragment(id="rule_a", text="A")
    reg.register(f)
    assert reg.has("rule_a")
    assert "rule_a" in reg
    assert reg.get("rule_a") is f
    assert len(reg) == 1


def test_registry_rejects_duplicate_ids():
    reg = FragmentRegistry()
    reg.register(Fragment(id="rule_a", text="A"))
    with pytest.raises(DuplicateFragmentError):
        reg.register(Fragment(id="rule_a", text="A2"))


def test_registry_get_missing_raises_eagerly():
    reg = FragmentRegistry()
    with pytest.raises(MissingFragmentError):
        reg.get("nope")


def test_registry_by_tag():
    reg = FragmentRegistry()
    f_voice = Fragment(id="a", text="A", tags=("voice", "invariant"))
    f_format = Fragment(id="b", text="B", tags=("format",))
    reg.register(f_voice)
    reg.register(f_format)
    assert reg.by_tag("voice") == (f_voice,)
    assert reg.by_tag("format") == (f_format,)
    assert reg.by_tag("nope") == ()


def test_registry_all_returns_registration_order():
    reg = FragmentRegistry()
    a = Fragment(id="a", text="A")
    b = Fragment(id="b", text="B")
    c = Fragment(id="c", text="C")
    for f in (b, a, c):
        reg.register(f)
    assert reg.all() == (b, a, c)


def test_registry_register_many():
    reg = FragmentRegistry()
    reg.register_many([Fragment(id="a", text="A"), Fragment(id="b", text="B")])
    assert reg.has("a") and reg.has("b")


# ---------------------------------------------------------------- Recipe


def test_recipe_requires_tuple_fragment_ids():
    with pytest.raises(TypeError):
        Recipe(id="r", fragment_ids=["a", "b"])  # type: ignore[arg-type]


def test_recipe_requires_nonempty_id():
    with pytest.raises(ValueError):
        Recipe(id="", fragment_ids=())


# ---------------------------------------------------------------- assemble


def test_assemble_empty_recipe_returns_empty_string():
    reg = FragmentRegistry()
    out = assemble(Recipe(id="r", fragment_ids=()), reg)
    assert out == ""


def test_assemble_orders_by_priority_descending():
    reg = FragmentRegistry()
    reg.register(Fragment(id="low", text="L", priority=10))
    reg.register(Fragment(id="high", text="H", priority=100))
    reg.register(Fragment(id="mid", text="M", priority=50))
    out = assemble(Recipe(id="r", fragment_ids=("low", "high", "mid")), reg)
    assert out == "H\nM\nL"


def test_assemble_deduplicates_by_id():
    reg = FragmentRegistry()
    reg.register(Fragment(id="a", text="A", priority=100))
    out = assemble(Recipe(id="r", fragment_ids=("a", "a", "a")), reg)
    assert out == "A"


def test_assemble_stable_within_same_priority():
    reg = FragmentRegistry()
    reg.register(Fragment(id="a", text="A", priority=100))
    reg.register(Fragment(id="b", text="B", priority=100))
    reg.register(Fragment(id="c", text="C", priority=100))
    out = assemble(Recipe(id="r", fragment_ids=("c", "a", "b")), reg)
    # Stable sort preserves first-seen order at equal priority.
    assert out == "C\nA\nB"


def test_assemble_raises_on_missing_fragment():
    reg = FragmentRegistry()
    reg.register(Fragment(id="a", text="A"))
    with pytest.raises(MissingFragmentError):
        assemble(Recipe(id="r", fragment_ids=("a", "ghost")), reg)


def test_assemble_custom_separator():
    reg = FragmentRegistry()
    reg.register(Fragment(id="a", text="A", priority=100))
    reg.register(Fragment(id="b", text="B", priority=50))
    out = assemble(Recipe(id="r", fragment_ids=("a", "b")), reg, separator=" | ")
    assert out == "A | B"
