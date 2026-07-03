"""Pack registry — discovers and holds the loaded character packs.

A directory of packs is scanned once; each subdirectory containing a
`pack.yaml` is loaded through the hardened loader. A single malformed or
malicious pack is logged and skipped rather than taking down the whole
registry — one bad community submission must not deny the others.
"""
from __future__ import annotations

import logging
import os

from engine.pack import CharacterPack, PackError, load_pack

_log = logging.getLogger("micro_engine.registry")


class PackRegistry:
    """Character packs keyed by their `meta.name` (the OpenAI model name)."""

    def __init__(self, packs: dict[str, CharacterPack] | None = None) -> None:
        self._packs = dict(packs or {})

    @classmethod
    def from_dir(cls, root: str) -> PackRegistry:
        packs: dict[str, CharacterPack] = {}
        if os.path.isdir(root):
            for entry in sorted(os.listdir(root)):
                sub = os.path.join(root, entry)
                if not os.path.isdir(sub):
                    continue
                try:
                    pack = load_pack(sub)
                except PackError as exc:
                    _log.warning("skipping pack %r: %s", entry, exc)
                    continue
                if pack.meta.name in packs:
                    _log.warning(
                        "duplicate pack name %r in %r; keeping the first",
                        pack.meta.name,
                        entry,
                    )
                    continue
                packs[pack.meta.name] = pack
        return cls(packs)

    def get(self, name: str) -> CharacterPack | None:
        return self._packs.get(name)

    def names(self) -> list[str]:
        return sorted(self._packs)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._packs

    def __len__(self) -> int:
        return len(self._packs)
