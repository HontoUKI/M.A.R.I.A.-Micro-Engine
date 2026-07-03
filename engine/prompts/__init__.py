"""Prompt assembly primitives: fragments, recipes and the registry."""

from engine.prompts.registry import (
    DuplicateFragmentError,
    Fragment,
    FragmentRegistry,
    MissingFragmentError,
    Recipe,
    assemble,
)

__all__ = [
    "DuplicateFragmentError",
    "Fragment",
    "FragmentRegistry",
    "MissingFragmentError",
    "Recipe",
    "assemble",
]
