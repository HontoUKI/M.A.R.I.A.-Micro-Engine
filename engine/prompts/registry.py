"""Prompt fragment / recipe primitives.

A prompt fragment is an atomic rule (e.g. "no unicode emoji") with a stable
id, a priority and optional tags / languages. Recipes are named, ordered
bundles of fragment ids that compose into a single deterministic text block.

This module is persona-neutral by design and contains zero character copy.
In the Micro-Engine there is no built-in fragment library: fragments are
declared by a character pack and registered at pack load time. Ported from
the public M.A.R.I.A. Core snapshot (prompt-fragment registry, Rebirth 1.0.2)
and trimmed to the community tier.

Design contracts:

- A `Fragment` is **immutable**. To change rule wording, register a new
  fragment id, do not mutate in place. This protects assembled prompt
  baselines from silent drift.
- A `FragmentRegistry` rejects duplicate ids by default. Callers that need
  multiple variants of "the same rule" use distinct ids.
- `assemble(recipe, registry)` is the only documented way to turn a recipe
  into text. It deduplicates by fragment id, then sorts by priority
  descending (stable), so the same recipe always produces the same string
  regardless of how callers ordered their fragment_ids.
- `MissingFragmentError` is raised eagerly when a recipe references an
  unknown fragment id — silent skipping would hide broken packs at runtime.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field


class MissingFragmentError(KeyError):
    """Raised when a recipe references a fragment id not in the registry."""


class DuplicateFragmentError(ValueError):
    """Raised when register() is called twice with the same fragment id."""


@dataclass(frozen=True)
class Fragment:
    """Atomic prompt rule.

    Fields:
        id:        stable canonical identifier (snake_case).
        text:      raw prompt text inserted verbatim into assembled output.
        priority:  higher numbers sort earlier in assembled output.
                   Convention: 100 = invariant rule, 50 = situational
                   nudge, 10 = tone overlay. Range is advisory, not
                   enforced.
        tags:      arbitrary tuple of string tags for filtering. Common
                   tags: "voice", "format", "boundary", "scenario".
        languages: tuple of language codes this fragment is written in
                   (e.g. ("en",), ("ru",), ("en", "ru")). Character packs
                   declare their own; the neutral default is ("en",).
    """

    id: str
    text: str
    priority: int = 100
    tags: tuple[str, ...] = ()
    languages: tuple[str, ...] = ("en",)

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ValueError("Fragment.id must be a non-empty string")
        if not isinstance(self.text, str):
            raise ValueError("Fragment.text must be a string")


@dataclass(frozen=True)
class Recipe:
    """Named bundle of fragment ids.

    Fields:
        id:           canonical recipe identifier (snake_case).
        fragment_ids: tuple of fragment ids to compose. Order in the
                      tuple does NOT determine output order — priority
                      does. Duplicate ids are silently deduplicated by
                      `assemble`.
        description:  one-line human description, never inlined into
                      the assembled prompt; for debug / docs only.
    """

    id: str
    fragment_ids: tuple[str, ...]
    description: str = ""

    def __post_init__(self) -> None:
        if not self.id or not isinstance(self.id, str):
            raise ValueError("Recipe.id must be a non-empty string")
        if not isinstance(self.fragment_ids, tuple):
            raise TypeError("Recipe.fragment_ids must be a tuple")


@dataclass
class FragmentRegistry:
    """Mutable collection of Fragments keyed by id.

    Registries are not thread-safe; the engine builds one registry per
    loaded character pack and treats it as read-mostly afterwards. Test
    code is free to construct ad-hoc registries.
    """

    _fragments: dict[str, Fragment] = field(default_factory=dict)

    def register(self, fragment: Fragment) -> None:
        if fragment.id in self._fragments:
            raise DuplicateFragmentError(
                f"fragment id already registered: {fragment.id!r}"
            )
        self._fragments[fragment.id] = fragment

    def register_many(self, fragments: Iterable[Fragment]) -> None:
        for fragment in fragments:
            self.register(fragment)

    def get(self, fragment_id: str) -> Fragment:
        try:
            return self._fragments[fragment_id]
        except KeyError as exc:
            raise MissingFragmentError(
                f"fragment id not found: {fragment_id!r}"
            ) from exc

    def has(self, fragment_id: str) -> bool:
        return fragment_id in self._fragments

    def all(self) -> tuple[Fragment, ...]:
        """Return every registered fragment in registration order."""
        return tuple(self._fragments.values())

    def by_tag(self, tag: str) -> tuple[Fragment, ...]:
        return tuple(f for f in self._fragments.values() if tag in f.tags)

    def __len__(self) -> int:
        return len(self._fragments)

    def __contains__(self, fragment_id: object) -> bool:
        return isinstance(fragment_id, str) and fragment_id in self._fragments


def assemble(
    recipe: Recipe,
    registry: FragmentRegistry,
    *,
    separator: str = "\n",
) -> str:
    """Resolve a recipe to a deterministic text block.

    Steps:
        1. Walk `recipe.fragment_ids` in declared order, looking each id
           up in the registry. Missing ids raise eagerly.
        2. Deduplicate by id (first occurrence wins).
        3. Sort by priority descending. Python's `sorted` is stable, so
           fragments at the same priority retain their first-seen order.
        4. Join `fragment.text` values with `separator`.

    Returns an empty string when the recipe has zero fragment_ids.
    """
    seen: set[str] = set()
    ordered: list[Fragment] = []
    for fid in recipe.fragment_ids:
        if fid in seen:
            continue
        seen.add(fid)
        ordered.append(registry.get(fid))
    ordered.sort(key=lambda f: -f.priority)
    return separator.join(f.text for f in ordered)


__all__ = [
    "DuplicateFragmentError",
    "Fragment",
    "FragmentRegistry",
    "MissingFragmentError",
    "Recipe",
    "assemble",
]
