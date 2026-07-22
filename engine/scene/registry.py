"""Scene registry — discovers and holds the loaded ScenePacks.

Mirrors the character `PackRegistry`: a directory of scenes is scanned once,
each subdirectory with a `scene.yaml` is loaded through the hardened loader, and
a single bad scene is logged and skipped rather than taking down the rest.
"""
from __future__ import annotations

import logging
import os

from engine.scene.errors import SceneError
from engine.scene.loader import load_scene
from engine.scene.models import ScenePack

_log = logging.getLogger("micro_engine.scene_registry")


class SceneRegistry:
    """ScenePacks keyed by their `meta.name`."""

    def __init__(self, scenes: dict[str, ScenePack] | None = None) -> None:
        self._scenes = dict(scenes or {})

    @classmethod
    def from_dir(cls, root: str) -> SceneRegistry:
        scenes: dict[str, ScenePack] = {}
        if os.path.isdir(root):
            for entry in sorted(os.listdir(root)):
                sub = os.path.join(root, entry)
                if not os.path.isdir(sub):
                    continue
                try:
                    scene = load_scene(sub)
                except SceneError as exc:
                    _log.warning("skipping scene %r: %s", entry, exc)
                    continue
                if scene.meta.name in scenes:
                    _log.warning(
                        "duplicate scene name %r in %r; keeping the first",
                        scene.meta.name,
                        entry,
                    )
                    continue
                scenes[scene.meta.name] = scene
        return cls(scenes)

    def get(self, name: str) -> ScenePack | None:
        return self._scenes.get(name)

    def names(self) -> list[str]:
        return sorted(self._scenes)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name in self._scenes

    def __len__(self) -> int:
        return len(self._scenes)
